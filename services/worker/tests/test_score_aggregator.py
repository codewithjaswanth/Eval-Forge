import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import pytest

# Add services/worker to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.evaluators.base import EvaluationResult, EvidenceItem
from analyzer.rubrics.aggregator import (
    ScoreAggregator,
    DEFAULT_RUBRIC_V1,
    CategoryScoreBreakdown,
    AggregatedScoreReport,
)
from analyzer.db import EvaluationDatabase


def test_rubric_weights_sum_to_exact_100():
    """Verify that DEFAULT_RUBRIC_V1 weights and max scores sum to exactly 100.00 points."""
    total_weights = sum(cat["weight"] for cat in DEFAULT_RUBRIC_V1.values())
    total_max_scores = sum(cat["max_score"] for cat in DEFAULT_RUBRIC_V1.values())

    assert pytest.approx(total_weights, 0.001) == 100.00
    assert pytest.approx(total_max_scores, 0.001) == 100.00
    assert len(DEFAULT_RUBRIC_V1) == 10


def test_score_aggregator_perfect_scores():
    """Verify that a perfect evaluation across all 10 evaluators aggregates to exactly 100.00."""
    aggregator = ScoreAggregator()
    results = {}

    for cat_key, cat_def in DEFAULT_RUBRIC_V1.items():
        eval_name = cat_def["evaluator"]
        results[eval_name] = EvaluationResult(
            criterion=cat_def["name"],
            score=cat_def["max_score"],
            maxScore=cat_def["max_score"],
            confidence=1.0,
            summary=f"Flawless performance in {cat_def['name']}",
            strengths=["Exemplary design", "Robust execution"],
            weaknesses=[],
            recommendations=[],
            evidence=[
                EvidenceItem(
                    source="linter.json",
                    metric="lint_errors",
                    value=0,
                    interpretation="Zero lint errors detected.",
                )
            ],
        )

    report = aggregator.aggregate(results, project_name="TestApp")
    assert report.overall_score == 100.00
    assert report.confidence == 1.00
    assert len(report.score_breakdown) == 10
    assert len(report.key_strengths) > 0
    assert len(report.key_weaknesses) == 0


def test_score_aggregator_partial_scores():
    """Verify deterministic weighted calculation with realistic mixed scores."""
    aggregator = ScoreAggregator()
    results = {}

    # Half score across all criteria
    for cat_key, cat_def in DEFAULT_RUBRIC_V1.items():
        eval_name = cat_def["evaluator"]
        results[eval_name] = EvaluationResult(
            criterion=cat_def["name"],
            score=cat_def["max_score"] / 2.0,
            maxScore=cat_def["max_score"],
            confidence=0.8,
            summary=f"Moderate performance in {cat_def['name']}",
            strengths=["Good start"],
            weaknesses=["Needs improvement"],
            recommendations=["Refactor"],
            evidence=[],
        )

    report = aggregator.aggregate(results, project_name="TestApp")
    assert report.overall_score == 50.00
    assert report.confidence == 0.80


def test_score_aggregator_missing_evaluator_unmeasurable():
    """Verify that missing evaluators are treated transparently as unmeasurable (0 points awarded)."""
    aggregator = ScoreAggregator()
    results = {
        "ProblemAnalyzer": EvaluationResult(
            criterion="Problem Statement",
            score=10.0,
            maxScore=10.0,
            confidence=0.9,
            summary="Clear problem definition.",
            strengths=["Well articulated"],
            weaknesses=[],
            recommendations=[],
            evidence=[],
        )
    }

    # Only 1 evaluator ran, 9 missing
    report = aggregator.aggregate(results, project_name="TestApp")

    # Problem statement is 10% of total
    assert report.overall_score == 10.00
    # Confidence is scaled by measured weight (10 / 100 * 0.9 = 0.09)
    assert pytest.approx(report.confidence, 0.01) == 0.09
    assert len(report.score_breakdown) == 10

    # Verify unmeasured criteria have 0 score and unmeasurable note
    code_quality_breakdown = report.score_breakdown["code_quality"]
    assert code_quality_breakdown["normalized_score"] == 0.00
    assert code_quality_breakdown["confidence"] == 0.00
    assert code_quality_breakdown["status"] == "missing"
    assert "was not executed" in code_quality_breakdown["summary"].lower()


def test_score_aggregator_clamping_out_of_bounds():
    """Verify aggregator clamps negative scores to 0 and excessive scores to max_score."""
    aggregator = ScoreAggregator()
    results = {
        "SecurityAnalyzer": EvaluationResult(
            criterion="Security",
            score=999.0,  # Exceeds max 10.0
            maxScore=10.0,
            confidence=1.5,  # Exceeds 1.0
            summary="Over-scored",
            strengths=[],
            weaknesses=[],
            recommendations=[],
            evidence=[],
        ),
        "OptimizationAnalyzer": EvaluationResult(
            criterion="Optimization",
            score=-50.0,  # Negative score
            maxScore=10.0,
            confidence=-0.2,  # Negative confidence
            summary="Under-scored",
            strengths=[],
            weaknesses=[],
            recommendations=[],
            evidence=[],
        ),
    }

    report = aggregator.aggregate(results, project_name="TestApp")
    sec_breakdown = report.score_breakdown["security"]
    assert sec_breakdown["raw_score"] == 10.00
    assert sec_breakdown["confidence"] == 1.00

    opt_breakdown = report.score_breakdown["optimization"]
    assert opt_breakdown["raw_score"] == 0.00
    assert opt_breakdown["confidence"] == 0.00


def test_stale_job_recovery_requeues_stuck_job():
    """Verify recover_stale_jobs identifies stranded jobs >15m old and requeues them if retries < 3."""
    db = EvaluationDatabase()

    # Create a job that has been stuck running for 20 minutes with retry_count = 0
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(minutes=20)).isoformat()

    stuck_run = {
        "id": "run-stuck-123",
        "project_id": "proj-1",
        "status": "running",
        "started_at": old_time,
        "retry_count": 0,
    }
    db.mock_runs[stuck_run["id"]] = stuck_run

    recovered = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert recovered == 1

    # Should be reset to queued with incremented retry count
    updated_run = db.mock_runs[stuck_run["id"]]
    assert updated_run["status"] == "queued"
    assert updated_run["retry_count"] == 1
    assert "Worker recovered stale job" in updated_run["error_information"]["reason"]


def test_stale_job_recovery_fails_job_after_max_retries():
    """Verify recover_stale_jobs marks a job failed if it has already been retried 3 times."""
    db = EvaluationDatabase()

    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(minutes=20)).isoformat()

    terminal_run = {
        "id": "run-stuck-terminal",
        "project_id": "proj-2",
        "status": "running",
        "started_at": old_time,
        "retry_count": 3,
    }
    db.mock_runs[terminal_run["id"]] = terminal_run

    recovered = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert recovered == 1

    # Should be set to failed
    updated_run = db.mock_runs[terminal_run["id"]]
    assert updated_run["status"] == "failed"
    assert "exceeded max retries" in updated_run["error_information"]["error"].lower()



def test_stale_job_recovery_ignores_recent_jobs():
    """Verify recover_stale_jobs does not interrupt jobs that started recently (< 15 mins ago)."""
    db = EvaluationDatabase()

    now = datetime.now(timezone.utc)
    recent_time = (now - timedelta(minutes=2)).isoformat()

    healthy_run = {
        "id": "run-healthy-active",
        "project_id": "proj-3",
        "status": "running",
        "started_at": recent_time,
        "retry_count": 0,
    }
    db.mock_runs[healthy_run["id"]] = healthy_run

    recovered = db.recover_stale_jobs(stale_threshold_seconds=900)
    assert recovered == 0
    assert db.mock_runs[healthy_run["id"]]["status"] == "running"


def test_rubric_invalid_weights_sum_rejected():
    """Verify that ScoreAggregator rejects any rubric whose weights do not sum to exactly 100.00."""
    invalid_rubric = {
        "problem_statement": {
            "name": "Problem",
            "evaluator": "ProblemAnalyzer",
            "weight": 50.0,
            "max_score": 10.0,
        },
        "solution_quality": {
            "name": "Solution",
            "evaluator": "SolutionAnalyzer",
            "weight": 40.0,  # Sum = 90.00, not 100.00!
            "max_score": 15.0,
        }
    }
    with pytest.raises(ValueError) as exc:
        ScoreAggregator(rubric_version="invalid-test", custom_rubric=invalid_rubric)
    assert "weights sum to 90.0, expected 100.00" in str(exc.value)


def test_score_reproducibility_deterministic():
    """Verify identical evaluator inputs deterministically produce bit-for-bit identical reports."""
    aggregator = ScoreAggregator()
    results = {
        "ProblemAnalyzer": EvaluationResult(criterion="Problem Statement", score=8.5, maxScore=10.0, confidence=0.9, summary="Clear"),
        "SolutionAnalyzer": EvaluationResult(criterion="Solution Quality", score=12.0, maxScore=15.0, confidence=0.85, summary="Sound"),
        "CodeQualityAnalyzer": EvaluationResult(criterion="Code Quality", score=14.0, maxScore=15.0, confidence=0.95, summary="Strong"),
    }

    report_1 = aggregator.aggregate(results, project_name="App")
    report_2 = aggregator.aggregate(results, project_name="App")

    assert report_1.overall_score == report_2.overall_score
    assert report_1.confidence == report_2.confidence
    assert report_1.score_breakdown == report_2.score_breakdown


def test_score_manipulation_defense():
    """Verify that anomalous or malicious scores exceeding max_score are clamped to rubric limits."""
    aggregator = ScoreAggregator()
    results = {
        "ProblemAnalyzer": EvaluationResult(
            criterion="Problem Statement",
            score=999999.0,  # Extreme inflation attempt
            maxScore=10.0,
            confidence=5.0,  # Extreme confidence inflation
            summary="Inflated",
        )
    }

    report = aggregator.aggregate(results, project_name="App")
    breakdown = report.score_breakdown["problem_statement"]
    assert breakdown["raw_score"] == 10.0
    assert breakdown["normalized_score"] == 10.0
    assert breakdown["confidence"] == 1.0

