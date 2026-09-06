import os
import sys
import time
import uuid
import logging
from typing import Optional
from pathlib import Path

from .db import EvaluationDatabase
from .sandbox import DisposableWorkspace
from .ingestion.git_client import GitClient, GitIngestionError
from .ingestion.detector import ProjectDetector
from .models import ProjectArtifact
from .observability import structured_logger
from .pipeline import PipelineOrchestrator
from .evaluators import get_standard_evaluators
from .rubrics.aggregator import ScoreAggregator
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("evalforge.worker")

class EvaluationWorker:
    """
    High-performance asynchronous evaluation worker that polls Supabase for queued runs,
    atomically claims jobs, creates disposable sandboxes, and ingests repositories.
    """
    def __init__(self, db: Optional[EvaluationDatabase] = None, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"worker_{uuid.uuid4().hex[:6]}"
        self.db = db or EvaluationDatabase()
        self.git_client = GitClient(timeout_seconds=60)
        self.detector = ProjectDetector()
        self.aggregator = ScoreAggregator()
        self.last_stale_recovery: float = 0.0

    def process_one_job(self) -> bool:
        """
        Polls and executes one queued evaluation job.
        Returns True if a job was found and processed, False if queue was empty.
        """
        # Periodic check to recover stalled runs from crashed worker processes (runs every 60s, not in hot polling path)
        now_t = time.time()
        if now_t - self.last_stale_recovery > 60.0:
            self.last_stale_recovery = now_t
            self.db.recover_stale_jobs(stale_threshold_seconds=900)

        run = self.db.claim_next_run(self.worker_id)
        if not run:
            return False

        run_id = run["id"]
        submission_id = run["submission_id"]
        logger.info(f"[{self.worker_id}] Starting evaluation for run: {run_id}")

        submission, project = self.db.get_submission_and_project(submission_id)
        if not project or not submission:
            error_msg = f"Missing project or submission record for submission_id: {submission_id}"
            logger.error(error_msg)
            self.db.mark_run_failed(run_id, error_msg)
            return True

        repo_url = project.get("repo_url")
        live_url = project.get("live_url")
        description = project.get("description")
        branch = submission.get("branch") or "main"

        try:
            # 1. Create isolated disposable sandbox
            with DisposableWorkspace(prefix="evalforge_") as workspace_path:
                logger.info(f"Cloning {repo_url} into sandbox {workspace_path}...")
                
                # 2. Shallow clone repository
                commit_sha, resolved_branch = self.git_client.clone_repository(
                    repo_url=repo_url,
                    target_dir=workspace_path,
                    branch=branch
                )

                # 3. Detect stack and build normalized ProjectArtifact
                artifact: ProjectArtifact = self.detector.detect_project(
                    root_path=workspace_path,
                    repository_url=repo_url,
                    commit_sha=commit_sha,
                    branch=resolved_branch,
                    live_url=live_url,
                    description=description
                )

                logger.info(f"Ingestion successful for {repo_url}:")
                logger.info(f"  - Languages: {artifact.detected_languages}")
                logger.info(f"  - Frameworks: {artifact.detected_frameworks}")
                logger.info(f"  - Package Managers: {artifact.package_managers}")
                logger.info(f"  - Has Frontend: {artifact.has_frontend}, Has Backend: {artifact.has_backend}")
                logger.info(f"  - Total Files: {len(artifact.file_tree)}, Test Files: {len(artifact.test_files)}")

                # 4. Record ingestion success in database
                self.db.record_ingestion_success(
                    run_id=run_id,
                    submission_id=submission_id,
                    artifact_dict=artifact.to_dict()
                )

                # 5. Execute concurrent evaluator pipeline
                orchestrator = PipelineOrchestrator(
                    evaluators=get_standard_evaluators(),
                    db=self.db,
                    worker_id=self.worker_id
                )
                results = asyncio.run(orchestrator.execute_pipeline(run_id=run_id, artifact=artifact))

                # Deterministically aggregate scores and generate report
                report = self.aggregator.aggregate(results, project_name=project.get("name", "Project"))

                # Persist the final report snapshot
                self.db.record_report(
                    run_id=run_id,
                    project_id=project["id"],
                    report_dict=report.to_dict()
                )

                self.db.mark_run_completed(
                    run_id=run_id,
                    overall_score=report.overall_score,
                    confidence=report.confidence
                )
                structured_logger.log_evaluation_event(
                    evaluation_run_id=run_id,
                    worker_id=self.worker_id,
                    status="completed",
                    message=f"Evaluation run completed with score {report.overall_score:.2f}/100",
                    extra={"overall_score": report.overall_score, "confidence": report.confidence}
                )
                logger.info(f"Evaluation run {run_id} completed. Overall score: {report.overall_score:.2f}/100 (Confidence: {report.confidence*100:.1f}%)")

        except GitIngestionError as ge:
            logger.error(f"Git ingestion failed for run {run_id}: {ge}")
            structured_logger.log_evaluation_event(
                evaluation_run_id=run_id,
                worker_id=self.worker_id,
                status="failed",
                error_category="git_ingestion_error",
                message=str(ge)
            )
            self.db.mark_run_failed(run_id, f"Git Ingestion Error: {str(ge)}")
        except Exception as ex:
            logger.error(f"Unexpected worker failure on run {run_id}: {ex}", exc_info=True)
            structured_logger.log_evaluation_event(
                evaluation_run_id=run_id,
                worker_id=self.worker_id,
                status="failed",
                error_category="worker_runtime_error",
                message=str(ex)
            )
            self.db.mark_run_failed(run_id, f"Worker Pipeline Error: {str(ex)}")

        return True

    def start_polling(
        self,
        poll_interval: float = 0.4,
        max_poll_interval: float = 1.5,
        max_iterations: Optional[int] = None
    ):
        """
        Continuously poll queue for jobs using fast adaptive intervals.
        Immediately claims new jobs within < 400ms when active, backing off gracefully when idle.
        """
        logger.info(f"EvalForge Worker [{self.worker_id}] online and polling queue (active: {poll_interval}s, idle: {max_poll_interval}s)...")
        iterations = 0
        current_interval = poll_interval
        consecutive_empty = 0
        try:
            while True:
                processed = self.process_one_job()
                iterations += 1
                if max_iterations and iterations >= max_iterations:
                    break
                if processed:
                    current_interval = poll_interval
                    consecutive_empty = 0
                else:
                    consecutive_empty += 1
                    if consecutive_empty > 3:
                        current_interval = min(max_poll_interval, current_interval * 1.3)
                    time.sleep(current_interval)
        except KeyboardInterrupt:
            logger.info(f"Worker [{self.worker_id}] shutting down gracefully.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="EvalForge Evaluation Worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--poll-interval", type=float, default=0.4, help="Fast poll interval in seconds (default: 0.4s)")
    args = parser.parse_args()

    worker = EvaluationWorker()
    if args.once:
        worker.process_one_job()
    else:
        worker.start_polling(poll_interval=args.poll_interval)

if __name__ == "__main__":
    main()
