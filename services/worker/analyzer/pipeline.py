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
        Executes all evaluators in the DAG according to dependency availability.
        Independent evaluators run concurrently.
        """
        completed: Dict[str, EvaluationResult] = {}
        failed_evaluators: Set[str] = set()
        skipped_evaluators: Set[str] = set()

        # Initialize all modules as 'pending' in database
        if self.db:
            for name, ev in self.evaluators.items():
                self.db.upsert_module_status(
                    run_id=run_id,
                    module_name=name,
                    status="pending",
                    max_score=ev.max_score
                )

        remaining_evaluators = set(self.evaluators.keys())

        async def run_single_evaluator(name: str):
            ev = self.evaluators[name]
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

            # Record completion or failure
            is_success = not result.is_error
            
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

            return name, result, is_success

        while remaining_evaluators:
            # 1. Identify evaluators ready to execute (all dependencies completed successfully)
            ready_to_run = []
            to_skip = []

            for name in list(remaining_evaluators):
                deps = set(self.evaluators[name].dependencies)
                # Check if any dependency has failed or was skipped
                if any(dep in failed_evaluators or dep in skipped_evaluators for dep in deps):
                    to_skip.append(name)
                # Check if all dependencies are satisfied
                elif deps.issubset(set(completed.keys())):
                    ready_to_run.append(name)

            # 2. Process skipped evaluators (cascade from dependency failures)
            for name in to_skip:
                ev = self.evaluators[name]
                logger.warning(f"[{name}] Skipped due to failed/missing prerequisite dependency.")
                skipped_evaluators.add(name)
                remaining_evaluators.remove(name)
                
                skip_result = EvaluationResult(
                    criterion=ev.criterion,
                    score=0.0,
                    maxScore=ev.max_score,
                    confidence=0.0,
                    summary=f"Skipped because dependency evaluation failed.",
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
                        error_information={"reason": "Dependency failure"}
                    )

            if not ready_to_run and remaining_evaluators:
                # Deadlock detection if any unaccounted nodes remain
                raise PipelineDependencyError(
                    f"Deadlock in evaluator pipeline. Remaining unsatisfied: {remaining_evaluators}"
                )

            if not ready_to_run:
                break

            # 3. Execute all ready evaluators CONCURRENTLY
            logger.info(f"Executing concurrent evaluator wave: {ready_to_run}")
            tasks = [run_single_evaluator(name) for name in ready_to_run]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for item in results:
                if isinstance(item, Exception):
                    logger.error(f"Unhandled pipeline task exception: {item}")
                    continue

                name, result, is_success = item
                remaining_evaluators.remove(name)
                completed[name] = result

                if not is_success:
                    failed_evaluators.add(name)

        logger.info(f"Pipeline finished for run {run_id}. Total evaluated modules: {len(completed)}")
        return completed
