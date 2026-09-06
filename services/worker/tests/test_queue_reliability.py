import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.db import EvaluationDatabase
from analyzer.evaluators.base import BaseEvaluator, EvaluationResult
from analyzer.pipeline import PipelineOrchestrator, PipelineDependencyError
from analyzer.models import ProjectArtifact

class HangingEvaluator(BaseEvaluator):
    """Evaluator that deliberately exceeds its timeout."""
    def __init__(self, timeout_seconds: float = 0.2):
        super().__init__(
            name="HangingEvaluator",
            criterion="hanging_check",
            max_score=10.0,
            timeout_seconds=timeout_seconds
        )

    async def execute(self, artifact, context):
        await asyncio.sleep(2.0)
        return EvaluationResult(criterion="hanging_check", score=10.0, maxScore=10.0, confidence=1.0, summary="Done")

class FailingEvaluator(BaseEvaluator):
    """Evaluator that throws an unexpected runtime error."""
    def __init__(self):
        super().__init__(
            name="FailingEvaluator",
            criterion="failing_check",
            max_score=10.0,
            timeout_seconds=5.0
        )

    async def execute(self, artifact, context):
        raise RuntimeError("Simulated evaluator core crash")

class DependentEvaluator(BaseEvaluator):
    """Evaluator depending on FailingEvaluator."""
    def __init__(self):
        super().__init__(
            name="DependentEvaluator",
            criterion="dependent_check",
            max_score=10.0,
            dependencies=["FailingEvaluator"]
        )

    async def execute(self, artifact, context):
        return EvaluationResult(criterion="dependent_check", score=10.0, maxScore=10.0, confidence=1.0, summary="Success")

def test_atomic_queue_claiming_prevents_duplicate_processing():
    """Verify that when multiple workers claim concurrently, only one receives the queued run."""
    db = EvaluationDatabase(use_mock=True)

    # Insert a single queued run
    run_id = "run-single-job-001"
    sub_id = "sub-001"
    db.mock_runs[run_id] = {
        "id": run_id,
        "submission_id": sub_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retry_count": 0
    }
    db.mock_submissions[sub_id] = {"id": sub_id, "project_id": "proj-001"}
    db.mock_projects["proj-001"] = {"id": "proj-001", "name": "test-repo", "repo_url": "https://github.com/test/repo"}

    # Worker 1 claims
    claimed_1 = db.claim_next_run(worker_id="worker_alpha")
    assert claimed_1 is not None
    assert claimed_1["id"] == run_id
    assert claimed_1["status"] == "running"
    assert claimed_1["worker_id"] == "worker_alpha"

    # Worker 2 attempts to claim simultaneously
    claimed_2 = db.claim_next_run(worker_id="worker_beta")
    assert claimed_2 is None  # Queue is empty, no double claiming

def test_worker_crash_stale_lease_recovery_lifecycle():
    """Verify complete recovery lifecycle: running -> stale detected -> requeued (retries < 3) -> terminal fail."""
    db = EvaluationDatabase(use_mock=True)
    stuck_time = (datetime.now(timezone.utc) - timedelta(minutes=25)).isoformat()

    run_id = "run-crashed-worker-lifecycle"
    db.mock_runs[run_id] = {
        "id": run_id,
        "status": "running",
        "started_at": stuck_time,
        "retry_count": 0,
        "worker_id": "crashed_worker_1"
    }

    # Attempt 1 recovery
    rec_1 = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert rec_1 == 1
    assert db.mock_runs[run_id]["status"] == "queued"
    assert db.mock_runs[run_id]["retry_count"] == 1
    assert db.mock_runs[run_id]["worker_id"] is None

    # Simulate worker claiming and crashing again on retry 1
    db.mock_runs[run_id]["status"] = "running"
    db.mock_runs[run_id]["started_at"] = stuck_time
    db.mock_runs[run_id]["worker_id"] = "crashed_worker_2"

    rec_2 = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert rec_2 == 1
    assert db.mock_runs[run_id]["status"] == "queued"
    assert db.mock_runs[run_id]["retry_count"] == 2

    # Simulate 3rd crash
    db.mock_runs[run_id]["status"] = "running"
    db.mock_runs[run_id]["started_at"] = stuck_time
    db.mock_runs[run_id]["worker_id"] = "crashed_worker_3"

    rec_3 = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert rec_3 == 1
    assert db.mock_runs[run_id]["status"] == "queued"
    assert db.mock_runs[run_id]["retry_count"] == 3

    # 4th crash: exceeds max retries (retries >= 3) -> must permanently FAIL
    db.mock_runs[run_id]["status"] = "running"
    db.mock_runs[run_id]["started_at"] = stuck_time
    rec_4 = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert rec_4 == 1
    assert db.mock_runs[run_id]["status"] == "failed"
    assert "exceeded max retries" in db.mock_runs[run_id]["error_information"]["error"].lower()

@pytest.mark.asyncio
async def test_evaluator_timeout_isolated_from_worker():
    """Verify an evaluator timing out does not crash the worker pipeline."""
    db = EvaluationDatabase(use_mock=True)
    hanging = HangingEvaluator(timeout_seconds=0.2)
    orchestrator = PipelineOrchestrator(evaluators=[hanging], db=db)

    artifact = ProjectArtifact(
        root_path=Path("."),
        source_type="git_clone",
        repository_url="https://github.com/org/repo",
        commit_sha="abc1234",
        branch="main"
    )

    results = await orchestrator.execute_pipeline(run_id="run-timeout-test", artifact=artifact)
    assert "HangingEvaluator" in results
    res = results["HangingEvaluator"]
    assert res.is_error is True
    assert "timed out" in res.error_message.lower()

@pytest.mark.asyncio
async def test_evaluator_failure_cascade_skips_dependents():
    """Verify failing evaluator cleanly fails and skips dependent evaluators without worker crash."""
    db = EvaluationDatabase(use_mock=True)
    failing = FailingEvaluator()
    dependent = DependentEvaluator()
    orchestrator = PipelineOrchestrator(evaluators=[failing, dependent], db=db)

    artifact = ProjectArtifact(
        root_path=Path("."),
        source_type="git_clone",
        repository_url="https://github.com/org/repo",
        commit_sha="abc1234",
        branch="main"
    )

    results = await orchestrator.execute_pipeline(run_id="run-cascade-test", artifact=artifact)
    assert "FailingEvaluator" in results
    assert results["FailingEvaluator"].is_error is True

    assert "DependentEvaluator" in results
    dep_res = results["DependentEvaluator"]
    assert dep_res.score == 0.0
    assert "Skipped because dependency evaluation failed" in dep_res.summary
