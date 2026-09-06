import unittest
import tempfile
import shutil
import json
import sys
from pathlib import Path

# Add services/worker to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.db import EvaluationDatabase
from analyzer.runner import EvaluationWorker
from analyzer.models import ProjectArtifact

class TestIngestionPipeline(unittest.TestCase):
    def setUp(self):
        # Create a sample project directory on disk to simulate an ingested repository
        self.test_dir = tempfile.mkdtemp(prefix="evalforge_test_repo_")
        self.repo_path = Path(self.test_dir)

        # 1. Write package.json (Next.js + React + Tailwind)
        pkg_json = {
            "name": "sample-app",
            "dependencies": {
                "next": "15.0.0",
                "react": "^19.0.0",
                "tailwindcss": "^3.4.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0"
            }
        }
        (self.repo_path / "package.json").write_text(json.dumps(pkg_json), encoding="utf-8")
        (self.repo_path / "package-lock.json").write_text("{}", encoding="utf-8")

        # 2. Write source files
        app_dir = self.repo_path / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "page.tsx").write_text("export default function Page() { return <h1>Hello</h1>; }", encoding="utf-8")
        
        api_dir = app_dir / "api" / "submissions"
        api_dir.mkdir(parents=True, exist_ok=True)
        (api_dir / "route.ts").write_text("export async function POST() { return new Response(); }", encoding="utf-8")

        # 3. Write README.md
        (self.repo_path / "README.md").write_text("# Sample App\nA comprehensive software project.", encoding="utf-8")

        # 4. Write tests
        tests_dir = self.repo_path / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "example.test.ts").write_text("test('works', () => expect(true).toBe(true));", encoding="utf-8")

        # 5. Write CI/CD
        ci_dir = self.repo_path / ".github" / "workflows"
        ci_dir.mkdir(parents=True, exist_ok=True)
        (ci_dir / "ci.yml").write_text("name: CI\non: [push]", encoding="utf-8")

        # 6. Write Dockerfile
        (self.repo_path / "Dockerfile").write_text("FROM node:20\nWORKDIR /app", encoding="utf-8")

        # 7. Write config files
        (self.repo_path / "tsconfig.json").write_text("{}", encoding="utf-8")

        # Initialize mock DB
        self.db = EvaluationDatabase(use_mock=True)

    def tearDown(self):
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_full_ingestion_flow(self):
        # Setup seeded submission & project in mock DB
        project_id = "proj_001"
        submission_id = "sub_001"
        run_id = "run_001"

        self.db.mock_projects[project_id] = {
            "id": project_id,
            "name": "Sample App",
            "repo_url": str(self.repo_path),  # local fixture path
            "live_url": None,
            "description": "A Next.js sample project for evaluation"
        }

        self.db.mock_submissions[submission_id] = {
            "id": submission_id,
            "project_id": project_id,
            "branch": "main",
            "status": "pending",
            "metadata": {}
        }

        self.db.mock_runs[run_id] = {
            "id": run_id,
            "submission_id": submission_id,
            "status": "queued",
            "worker_id": None
        }

        # Initialize worker and process job
        worker = EvaluationWorker(db=self.db, worker_id="test_worker_1")
        processed = worker.process_one_job()

        self.assertTrue(processed, "Worker should claim and process the queued job")
        
        # Verify run status
        completed_run = self.db.mock_runs[run_id]
        self.assertEqual(completed_run["status"], "completed")
        self.assertEqual(completed_run["worker_id"], "test_worker_1")
        self.assertIsNotNone(completed_run["started_at"])
        self.assertIsNotNone(completed_run["completed_at"])

        # Verify submission metadata
        updated_sub = self.db.mock_submissions[submission_id]
        self.assertEqual(updated_sub["status"], "processed")
        meta = updated_sub["metadata"]

        # Validate extracted metadata
        self.assertIn("TypeScript", meta["detected_languages"])
        self.assertIn("Next.js", meta["detected_frameworks"])
        self.assertIn("React", meta["detected_frameworks"])
        self.assertIn("Tailwind CSS", meta["detected_frameworks"])
        self.assertIn("npm", meta["package_managers"])
        self.assertTrue(meta["has_frontend"])
        self.assertTrue(meta["has_backend"])
        self.assertTrue(meta["has_readme"])
        self.assertGreater(len(meta["test_directories"]), 0)
        self.assertGreater(meta["test_files_count"], 0)
        self.assertIn(".github/workflows/ci.yml", meta["ci_cd_workflows"])
        self.assertIn("Dockerfile", meta["docker_files"])
        self.assertIn("tsconfig.json", meta["config_files"])

    def test_idempotent_failure_handling(self):
        # Verify that a corrupt / unreachable repository gracefully sets run status to 'failed'
        project_id = "proj_bad"
        submission_id = "sub_bad"
        run_id = "run_bad"

        self.db.mock_projects[project_id] = {
            "id": project_id,
            "name": "Nonexistent App",
            "repo_url": "https://github.com/nonexistent_evalforge_fake/does_not_exist_404",
            "live_url": None,
            "description": None
        }
        self.db.mock_submissions[submission_id] = {
            "id": submission_id,
            "project_id": project_id,
            "branch": "main",
            "status": "pending",
            "metadata": {}
        }
        self.db.mock_runs[run_id] = {
            "id": run_id,
            "submission_id": submission_id,
            "status": "queued",
            "worker_id": None
        }

        worker = EvaluationWorker(db=self.db, worker_id="test_worker_fail")
        processed = worker.process_one_job()

        self.assertTrue(processed)
        failed_run = self.db.mock_runs[run_id]
        self.assertEqual(failed_run["status"], "failed")
        self.assertIn("error", failed_run["error_information"])

if __name__ == "__main__":
    unittest.main()
