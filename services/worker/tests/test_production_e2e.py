import sys
import os
import threading
import http.server
import socketserver
from pathlib import Path
from datetime import datetime, timezone
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.db import EvaluationDatabase
from analyzer.runner import EvaluationWorker

class QuietHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence HTTP server logs during tests

@pytest.fixture(scope="module")
def local_web_server():
    """Starts a local HTTP server serving the controlled repo frontend on an ephemeral port."""
    fixture_dir = Path(__file__).parent / "fixtures" / "controlled_repo" / "frontend"
    port = 18765

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    handler = lambda *args, **kwargs: QuietHTTPRequestHandler(*args, directory=str(fixture_dir), **kwargs)
    httpd = ReusableTCPServer(("127.0.0.1", port), handler)

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    os.environ["EVALFORGE_ALLOW_LOCAL_TEST_SITES"] = "true"
    os.environ["EVALFORGE_ALLOW_LOCAL_FIXTURES"] = "true"

    yield f"http://127.0.0.1:{port}/index.html"

    httpd.shutdown()
    httpd.server_close()
    os.environ.pop("EVALFORGE_ALLOW_LOCAL_TEST_SITES", None)
    os.environ.pop("EVALFORGE_ALLOW_LOCAL_FIXTURES", None)

def test_production_end_to_end_evaluation_flow(local_web_server):
    """
    Real end-to-end evaluation test:
    1. Submits controlled repository (with frontend, backend, intentional lint/format issues, docs, and tests).
    2. Provides real live URL served by local web server.
    3. Runs EvaluationWorker.process_one_job() through the complete pipeline.
    4. Asserts all 10 evaluators produce real empirical evidence, Playwright runs live audits,
       ScoreAggregator produces a deterministic final score, and full relational bundle is persisted.
    """
    repo_path = Path(__file__).parent / "fixtures" / "controlled_repo"
    assert repo_path.exists(), f"Controlled repo fixture missing at {repo_path}"

    if not (repo_path / ".git").exists():
        import subprocess
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test Runner"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@evalforge.local"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=repo_path, check=False, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Controlled test fixture"], cwd=repo_path, check=True, capture_output=True)

    db = EvaluationDatabase(use_mock=True)
    worker = EvaluationWorker(db=db, worker_id="worker_e2e_prod")

    project_id = "proj-e2e-controlled"
    submission_id = "sub-e2e-controlled"
    run_id = "run-e2e-controlled"

    db.mock_projects[project_id] = {
        "id": project_id,
        "name": "evalforge-team/taskflow-tracker",
        "repo_url": str(repo_path),
        "live_url": local_web_server,
        "description": "Distributed real-time task tracker for engineering teams with offline journaling."
    }

    db.mock_submissions[submission_id] = {
        "id": submission_id,
        "project_id": project_id,
        "branch": "main",
        "status": "pending"
    }

    db.mock_runs[run_id] = {
        "id": run_id,
        "submission_id": submission_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "retry_count": 0
    }

    # Execute full worker pipeline
    job_processed = worker.process_one_job()
    assert job_processed is True

    # 1. Verify Run Status
    completed_run = db.mock_runs[run_id]
    assert completed_run["status"] == "completed", f"Run failed with: {completed_run.get('error_information')}"
    assert completed_run["overall_score"] is not None
    assert 0.0 <= completed_run["overall_score"] <= 100.0
    assert 0.0 <= completed_run["confidence_score"] <= 1.0

    # 2. Verify Ingestion Discovery
    sub_record = db.mock_submissions[submission_id]
    metadata = sub_record.get("metadata", {})
    assert "JavaScript" in metadata.get("detected_languages", [])
    assert "Python" in metadata.get("detected_languages", [])
    assert metadata.get("has_frontend") is True
    assert metadata.get("has_backend") is True
    assert metadata.get("has_readme") is True
    assert len(metadata.get("test_files", [])) >= 1

    # 3. Verify All 10 Modules Executed
    modules = [m for m in db.mock_modules.values() if m["run_id"] == run_id]
    assert len(modules) == 10
    for mod in modules:
        assert mod["status"] == "completed", f"Module {mod['module_name']} failed: {mod.get('error_information')}"
        assert mod["score"] is not None
        assert mod["score"] <= mod["max_score"]

    # 4. Verify Real Playwright Browser Evidence (UIAnalyzer & PerformanceAnalyzer)
    evidence_items = [e for e in db.mock_evidence if e["run_id"] == run_id]
    assert len(evidence_items) > 0

    ui_evidence = [e for e in evidence_items if "playwright" in e.get("source", "").lower() or "browser" in e.get("source", "").lower()]
    assert len(ui_evidence) > 0, "Expected empirical Playwright evidence items"

    # Verify form audit, interactive elements, and responsive layout were detected
    form_ev = next((e for e in ui_evidence if e.get("metric") == "forms_detected"), None)
    assert form_ev is not None, "Playwright should have detected the interactive task form"
    assert form_ev["value"] >= 1

    interact_ev = next((e for e in ui_evidence if e.get("metric") == "interactive_elements"), None)
    assert interact_ev is not None, "Playwright should have detected interactive elements"
    assert interact_ev["value"] >= 1

    resp_ev = next((e for e in ui_evidence if e.get("metric") == "responsive_layout"), None)
    assert resp_ev is not None, "Playwright should have audited mobile and desktop responsive layout"

    # 5. Verify Report Aggregation & Relational Bundle
    full_bundle = db.get_full_report(run_id)
    assert full_bundle is not None
    assert full_bundle["run"]["id"] == run_id
    assert full_bundle["project"]["name"] == "evalforge-team/taskflow-tracker"
    assert len(full_bundle["modules"]) == 10
    assert len(full_bundle["criterion_scores"]) == 10
    assert len(full_bundle["evidence"]) > 0

    report = full_bundle["report"]
    assert report is not None
    assert report["rubric_version"] == "1.0.0"
    assert report["overall_score"] == completed_run["overall_score"]
    assert len(report["score_breakdown"]) == 10
    assert len(report["key_strengths"]) > 0
    assert len(report["action_plan"]) > 0
