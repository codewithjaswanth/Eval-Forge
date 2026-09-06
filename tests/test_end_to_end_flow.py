import unittest
import tempfile
import shutil
import json
import sys
import os
from pathlib import Path

# Add services/worker to sys.path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir / "services" / "worker"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from analyzer.db import EvaluationDatabase
from analyzer.runner import EvaluationWorker
from analyzer.ingestion.detector import ProjectDetector
from analyzer.sandbox import DisposableWorkspace

class TestEndToEndSubmissionPipeline(unittest.TestCase):
    def setUp(self):
        # Create a test fixture repository mimicking a real web application
        self.temp_dir = tempfile.mkdtemp(prefix="evalforge_e2e_fixture_")
        self.repo_dir = Path(self.temp_dir)

        # 1. Package.json (Next.js, React, Tailwind CSS, TypeScript)
        pkg = {
            "name": "evalforge-demo-app",
            "version": "1.0.0",
            "dependencies": {
                "next": "^15.1.0",
                "react": "^19.0.0",
                "react-dom": "^19.0.0",
                "tailwindcss": "^3.4.1"
            },
            "devDependencies": {
                "typescript": "^5.3.3",
                "eslint": "^8.56.0"
            }
        }
        (self.repo_dir / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
        (self.repo_dir / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'", encoding="utf-8")

        # 2. Source Code
        app_dir = self.repo_dir / "src" / "app"
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / "page.tsx").write_text("export default function Page() { return <div>EvalForge</div>; }", encoding="utf-8")

        api_dir = self.repo_dir / "src" / "app" / "api" / "analyze"
        api_dir.mkdir(parents=True, exist_ok=True)
        (api_dir / "route.ts").write_text("export async function POST() { return Response.json({ ok: true }); }", encoding="utf-8")

        # 3. README.md
        (self.repo_dir / "README.md").write_text("# EvalForge Demo App\nProduction-ready full-stack application.", encoding="utf-8")

        # 4. Tests
        tests_dir = self.repo_dir / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "app.test.tsx").write_text("describe('App', () => { it('renders', () => {}); });", encoding="utf-8")

        # 5. CI/CD Workflows
        workflows_dir = self.repo_dir / ".github" / "workflows"
        workflows_dir.mkdir(parents=True, exist_ok=True)
        (workflows_dir / "test.yml").write_text("name: Test\non: [push]", encoding="utf-8")

        # 6. Docker
        (self.repo_dir / "Dockerfile").write_text("FROM node:20-alpine\nWORKDIR /app", encoding="utf-8")
        (self.repo_dir / "docker-compose.yml").write_text("version: '3.8'\nservices:\n  web:\n    build: .", encoding="utf-8")

        # 7. Configurations
        (self.repo_dir / "tsconfig.json").write_text("{}", encoding="utf-8")
        (self.repo_dir / "tailwind.config.ts").write_text("export default {};", encoding="utf-8")
        (self.repo_dir / ".env.example").write_text("DATABASE_URL=postgres://...", encoding="utf-8")

        self.db = EvaluationDatabase(use_mock=True)

    def tearDown(self):
        if Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_full_pipeline_submission_to_metadata(self):
        """
        Verify:
        1. Project & Submission creation with queued status
        2. Worker atomic claiming
        3. Disposable workspace isolation and cleanup
        4. Metadata extraction (languages, frameworks, pkg mgrs, frontend/backend, tests, CI, docker)
        5. Completed status update
        """
        project_id = "proj_test_e2e_101"
        submission_id = "sub_test_e2e_101"
        run_id = "run_test_e2e_101"

        # Step 1: Simulate Submission creation
        self.db.mock_projects[project_id] = {
            "id": project_id,
            "name": "owner/evalforge-demo-app",
            "repo_url": str(self.repo_dir),
            "live_url": "https://evalforge-demo.vercel.app",
            "description": "Production full-stack demo application"
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
            "rubric_version": "1.0.0",
            "status": "queued",
            "worker_id": None
        }

        # Step 2: Worker claims and executes job
        worker = EvaluationWorker(db=self.db, worker_id="worker_e2e_alpha")
        success = worker.process_one_job()
        self.assertTrue(success, "Worker must claim and process the queued job")

        # Step 3: Assert evaluation run completed
        run = self.db.mock_runs[run_id]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(run["worker_id"], "worker_e2e_alpha")
        self.assertIsNotNone(run["started_at"])
        self.assertIsNotNone(run["completed_at"])

        # Step 4: Assert submission metadata matches the extracted ProjectArtifact
        sub = self.db.mock_submissions[submission_id]
        self.assertEqual(sub["status"], "processed")
        meta = sub["metadata"]

        # Languages
        self.assertIn("TypeScript", meta["detected_languages"])

        # Frameworks
        self.assertIn("Next.js", meta["detected_frameworks"])
        self.assertIn("React", meta["detected_frameworks"])
        self.assertIn("Tailwind CSS", meta["detected_frameworks"])

        # Package Managers
        self.assertIn("pnpm", meta["package_managers"])
        self.assertIn("npm", meta["package_managers"])

        # Architecture & Files
        self.assertTrue(meta["has_frontend"], "Next.js pages must be flagged as frontend")
        self.assertTrue(meta["has_backend"], "API routes must be flagged as backend")
        self.assertTrue(meta["has_readme"], "README must be detected")
        self.assertIn(".github/workflows/test.yml", meta["ci_cd_workflows"])
        self.assertIn("Dockerfile", meta["docker_files"])
        self.assertIn("docker-compose.yml", meta["docker_files"])
        self.assertIn("tsconfig.json", meta["config_files"])
        self.assertIn("tailwind.config.ts", meta["config_files"])
        self.assertGreater(meta["test_files_count"], 0)

        print("\n✅ End-to-end pipeline successfully verified:")
        print(f"   - Run: {run_id} ({run['status']})")
        print(f"   - Detected Languages: {meta['detected_languages']}")
        print(f"   - Detected Frameworks: {meta['detected_frameworks']}")
        print(f"   - Package Managers: {meta['package_managers']}")
        print(f"   - Architecture: Frontend={meta['has_frontend']}, Backend={meta['has_backend']}")
        print(f"   - Workflows: {meta['ci_cd_workflows']}")
        print(f"   - Docker: {meta['docker_files']}")

if __name__ == "__main__":
    unittest.main()
