import asyncio
import time
import logging
from datetime import datetime, timezone
from typing import List, Dict, Set, Any, Optional

from .models import ProjectArtifact
from .evaluators.base import BaseEvaluator, EvaluationResult
from .db import EvaluationDatabase
from .observability import structured_logger

logger = logging.getLogger("evalforge.pipeline")

class PipelineDependencyError(Exception):
    pass

class PipelineOrchestrator:
    """
    Dependency-aware concurrent pipeline orchestrator.
    Resolves the evaluator DAG, executes independent evaluators concurrently,
    persists incremental module progress to Supabase, and safely isolates failures.
    """
    def __init__(
        self,
        evaluators: List[BaseEvaluator],
        db: Optional[EvaluationDatabase] = None,
        worker_id: str = "worker"
    ):
        self.evaluators = {e.name: e for e in evaluators}
        self.db = db
        self.worker_id = worker_id
        self._validate_dag()

    def _validate_dag(self):
        """Validate that evaluator dependencies form a valid Directed Acyclic Graph (DAG)."""
        visited = set()
        rec_stack = set()

        def dfs(node: str):
            visited.add(node)
            rec_stack.add(node)

            evaluator = self.evaluators.get(node)
            if not evaluator:
                raise PipelineDependencyError(f"Evaluator '{node}' declared as a dependency but does not exist.")

            for dep in evaluator.dependencies:
                if dep not in self.evaluators:
                    raise PipelineDependencyError(f"Evaluator '{node}' depends on unknown evaluator '{dep}'")
                if dep in rec_stack:
                    raise PipelineDependencyError(f"Cyclic dependency detected: {node} -> {dep}")
                if dep not in visited:
                    dfs(dep)

            rec_stack.remove(node)

        for name in self.evaluators:
            if name not in visited:
                dfs(name)

    async def execute_pipeline(
        self,
        run_id: str,
        artifact: ProjectArtifact
    ) -> Dict[str, EvaluationResult]:
        """
        Executes all evaluators concurrently using an event-driven dependency DAG.
        Nodes launch the instant all their prerequisites finish without wave-level blocking.
        Every completion is immediately persisted to Supabase/localStore.
        """
        completed: Dict[str, EvaluationResult] = {}
        failed_evaluators: Set[str] = set()
        skipped_evaluators: Set[str] = set()
        events: Dict[str, asyncio.Event] = {name: asyncio.Event() for name in self.evaluators}

        # 1. Batch initialize all modules as 'pending' in database in ONE operation
        if self.db:
            if hasattr(self.db, "batch_upsert_modules"):
                module_defs = [
                    {"module_name": name, "status": "pending", "max_score": ev.max_score}
                    for name, ev in self.evaluators.items()
                ]
                self.db.batch_upsert_modules(run_id, module_defs)
            else:
                for name, ev in self.evaluators.items():
                    self.db.upsert_module_status(
                        run_id=run_id,
                        module_name=name,
                        status="pending",
                        max_score=ev.max_score
                    )

        async def run_single_evaluator(name: str):
            ev = self.evaluators[name]

            # Wait for all prerequisite dependencies to complete
            for dep in ev.dependencies:
                await events[dep].wait()
                if dep in failed_evaluators or dep in skipped_evaluators:
                    # Prerequisite failed: mark this node as skipped immediately
                    logger.warning(f"[{name}] Skipped because dependency '{dep}' did not succeed.")
                    skipped_evaluators.add(name)
                    skip_result = EvaluationResult(
                        criterion=ev.criterion,
                        score=0.0,
                        maxScore=ev.max_score,
                        confidence=0.0,
                        summary=f"Skipped because dependency evaluation failed: Prerequisite '{dep}' did not succeed.",
                        weaknesses=["Prerequisite module did not complete successfully."]
                    )
                    completed[name] = skip_result
                    if self.db:
                        self.db.upsert_module_status(
                            run_id=run_id,
                            module_name=name,
                            status="skipped",
                            score=0.0,
                            max_score=ev.max_score,
                            confidence=0.0,
                            error_information={"reason": f"Prerequisite '{dep}' failure"}
                        )
                    events[name].set()
                    return

            # All dependencies satisfied: mark node running immediately
            started_at = datetime.now(timezone.utc).isoformat()
            if self.db:
                self.db.upsert_module_status(
                    run_id=run_id,
                    module_name=name,
                    status="running",
                    max_score=ev.max_score,
                    started_at=started_at
                )

            # Execute evaluator safely with timeout handling
            t0 = time.monotonic()
            result = await ev.run_safe(artifact=artifact, context=completed)
            duration_ms = (time.monotonic() - t0) * 1000.0
            completed_at = datetime.now(timezone.utc).isoformat()
            is_success = not result.is_error

            completed[name] = result
            if not is_success:
                failed_evaluators.add(name)

            # Emit structured telemetry
            structured_logger.log_evaluation_event(
                evaluation_run_id=run_id,
                worker_id=self.worker_id,
                evaluator=name,
                duration_ms=duration_ms,
                status="completed" if is_success else "failed",
                error_category="evaluator_runtime_error" if not is_success else None,
                message=result.summary if is_success else result.error_message
            )

            # Persist completion or failure immediately so the UI reflects live progress
            if self.db:
                status_str = "completed" if is_success else "failed"
                mod_id = self.db.upsert_module_status(
                    run_id=run_id,
                    module_name=name,
                    status=status_str,
                    score=result.score,
                    max_score=result.maxScore,
                    confidence=result.confidence,
                    error_information={"summary": result.summary, "error": result.error_message} if not is_success else None,
                    started_at=started_at,
                    completed_at=completed_at
                )

                score_id = self.db.record_criterion_score(
                    run_id=run_id,
                    module_id=mod_id,
                    result=result
                )

                if result.evidence:
                    self.db.record_evidence(
                        run_id=run_id,
                        criterion_score_id=score_id,
                        evidence_list=result.evidence
                    )

            # Signal downstream dependents that this node has completed
            events[name].set()

        # Launch all 10 evaluators as non-blocking concurrent asyncio tasks
        tasks = [asyncio.create_task(run_single_evaluator(name)) for name in self.evaluators]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Pipeline finished for run {run_id}. Total evaluated modules: {len(completed)}")
        return completed
