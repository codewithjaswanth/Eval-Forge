import unittest
import asyncio
import time
import sys
from pathlib import Path
from typing import Dict

# Add services/worker to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from analyzer.models import ProjectArtifact
from analyzer.db import EvaluationDatabase
from analyzer.evaluators.base import BaseEvaluator, EvaluationResult, EvidenceItem
from analyzer.evaluators import (
    ProblemAnalyzer,
    SolutionAnalyzer,
    CodeQualityAnalyzer,
    OptimizationAnalyzer,
    UIAnalyzer,
    PerformanceAnalyzer,
    SecurityAnalyzer,
    NoveltyAnalyzer,
    DocumentationAnalyzer,
    EngineeringAnalyzer,
    get_standard_evaluators
)
from analyzer.pipeline import PipelineOrchestrator, PipelineDependencyError

def make_mock_artifact():
    return ProjectArtifact(
        root_path=Path("/tmp/mock_repo"),
        source_type="test_fixture",
        repository_url="https://github.com/test-org/test-project",
        commit_sha="a1b2c3d4e5f60000000000000000000000000000",
        branch="main",
        live_url=None,
        description="A robust web application for automated evaluation testing.",
        detected_languages=["TypeScript", "JavaScript"],
        detected_frameworks=["Next.js", "React", "Tailwind CSS"],
        package_managers=["npm", "pnpm"],
        build_systems=["Turbopack", "Vite"],
        has_frontend=True,
        has_backend=True,
        has_readme=True,
        readme_content="# Test Project\nGetting started: npm install && npm run dev",
        test_directories=["tests"],
        test_files=["tests/app.test.ts"],
        ci_cd_workflows=[".github/workflows/ci.yml"],
        docker_files=["Dockerfile"],
        config_files=["tsconfig.json", "tailwind.config.ts"],
        file_tree=["app/page.tsx", "tests/app.test.ts", "package.json"]
    )

class TestEvaluatorFramework(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_artifact = make_mock_artifact()
        self.mock_db = EvaluationDatabase(use_mock=True)

    # --------------------------------------------------------------------------
    # 1. Dependency Resolution & DAG Validation Tests
    # --------------------------------------------------------------------------
    def test_standard_evaluators_dag_validity(self):
        evaluators = get_standard_evaluators()
        orchestrator = PipelineOrchestrator(evaluators=evaluators, db=self.mock_db)
        self.assertEqual(len(orchestrator.evaluators), 10)
        self.assertEqual(orchestrator.evaluators["SolutionAnalyzer"].dependencies, ["ProblemAnalyzer"])
        self.assertIn("ProblemAnalyzer", orchestrator.evaluators["NoveltyAnalyzer"].dependencies)
        self.assertIn("SolutionAnalyzer", orchestrator.evaluators["NoveltyAnalyzer"].dependencies)
        self.assertEqual(orchestrator.evaluators["SecurityAnalyzer"].dependencies, ["CodeQualityAnalyzer"])
        self.assertEqual(orchestrator.evaluators["PerformanceAnalyzer"].dependencies, ["UIAnalyzer"])

    def test_cyclic_dependency_detection(self):
        class CycleA(BaseEvaluator):
            def __init__(self):
                super().__init__("CycleA", "crit_a", 10.0, dependencies=["CycleB"])
            async def execute(self, a, c): return None

        class CycleB(BaseEvaluator):
            def __init__(self):
                super().__init__("CycleB", "crit_b", 10.0, dependencies=["CycleA"])
            async def execute(self, a, c): return None

        with self.assertRaises(PipelineDependencyError) as ctx:
            PipelineOrchestrator([CycleA(), CycleB()])
        self.assertIn("Cyclic dependency detected", str(ctx.exception))

    def test_missing_dependency_detection(self):
        class BrokenNode(BaseEvaluator):
            def __init__(self):
                super().__init__("BrokenNode", "crit_broken", 10.0, dependencies=["NonExistentEvaluator"])
            async def execute(self, a, c): return None

        with self.assertRaises(PipelineDependencyError) as ctx:
            PipelineOrchestrator([BrokenNode()])
        self.assertIn("depends on unknown evaluator", str(ctx.exception))

    # --------------------------------------------------------------------------
    # 2. Concurrency Scheduling Tests
    # --------------------------------------------------------------------------
    async def test_concurrency_scheduling(self):
        """
        Verify independent evaluators run concurrently rather than sequentially.
        """
        timeline = {}

        class SlowIndependentA(BaseEvaluator):
            def __init__(self):
                super().__init__("SlowA", "crit_a", 10.0, dependencies=[])
            async def execute(self, artifact, context):
                timeline["SlowA_start"] = time.monotonic()
                await asyncio.sleep(0.15)
                timeline["SlowA_end"] = time.monotonic()
                return EvaluationResult("crit_a", 10.0, 10.0, 1.0, "Done A")

        class SlowIndependentB(BaseEvaluator):
            def __init__(self):
                super().__init__("SlowB", "crit_b", 10.0, dependencies=[])
            async def execute(self, artifact, context):
                timeline["SlowB_start"] = time.monotonic()
                await asyncio.sleep(0.15)
                timeline["SlowB_end"] = time.monotonic()
                return EvaluationResult("crit_b", 10.0, 10.0, 1.0, "Done B")

        class DependentC(BaseEvaluator):
            def __init__(self):
                super().__init__("DepC", "crit_c", 10.0, dependencies=["SlowA", "SlowB"])
            async def execute(self, artifact, context):
                timeline["DepC_start"] = time.monotonic()
                timeline["DepC_end"] = time.monotonic()
                return EvaluationResult("crit_c", 10.0, 10.0, 1.0, "Done C")

        orchestrator = PipelineOrchestrator(
            [SlowIndependentA(), SlowIndependentB(), DependentC()],
            db=self.mock_db
        )

        t0 = time.monotonic()
        results = await orchestrator.execute_pipeline(run_id="run_concurrent_test", artifact=self.mock_artifact)
        total_elapsed = time.monotonic() - t0

        # Concurrently, total time is ~0.15s - 0.25s (sequential would be >= 0.30s)
        self.assertLess(total_elapsed, 0.28, f"Independent evaluators must run concurrently (took {total_elapsed:.3f}s)")
        self.assertGreaterEqual(timeline["DepC_start"], timeline["SlowA_end"])
        self.assertGreaterEqual(timeline["DepC_start"], timeline["SlowB_end"])
        self.assertEqual(len(results), 3)

    # --------------------------------------------------------------------------
    # 3. Failure Handling & Dependency Cascade Skip Tests
    # --------------------------------------------------------------------------
    async def test_failure_handling_and_cascade_skip(self):
        """
        Verify:
        - If Evaluator A fails, independent Evaluator B still completes successfully.
        - Evaluator C (which depends on A) is marked 'skipped'.
        """
        class FailingNode(BaseEvaluator):
            def __init__(self):
                super().__init__("FailingNode", "crit_fail", 10.0, dependencies=[])
            async def execute(self, artifact, context):
                raise RuntimeError("Deliberate node crash for failure testing")

        class IndependentHealthy(BaseEvaluator):
            def __init__(self):
                super().__init__("HealthyNode", "crit_healthy", 10.0, dependencies=[])
            async def execute(self, artifact, context):
                return EvaluationResult("crit_healthy", 8.0, 10.0, 1.0, "Healthy result")

        class DependentOnFailure(BaseEvaluator):
            def __init__(self):
                super().__init__("DependentNode", "crit_dep", 10.0, dependencies=["FailingNode"])
            async def execute(self, artifact, context):
                return EvaluationResult("crit_dep", 10.0, 10.0, 1.0, "Should not run")

        orchestrator = PipelineOrchestrator(
            [FailingNode(), IndependentHealthy(), DependentOnFailure()],
            db=self.mock_db
        )

        results = await orchestrator.execute_pipeline(run_id="run_failure_test", artifact=self.mock_artifact)

        # Failing node was captured safely without crashing pipeline
        self.assertIn("FailingNode", results)
        self.assertEqual(results["FailingNode"].score, 0.0)
        self.assertIn("Deliberate node crash", results["FailingNode"].summary)

        # Independent healthy node completed successfully
        self.assertIn("HealthyNode", results)
        self.assertEqual(results["HealthyNode"].score, 8.0)

        # Dependent node was skipped
        self.assertIn("DependentNode", results)
        self.assertEqual(results["DependentNode"].score, 0.0)
        self.assertIn("Skipped", results["DependentNode"].summary)

        # Verify DB module statuses
        modules = self.mock_db.mock_modules
        self.assertEqual(modules["mod_run_failure_test_FailingNode"]["status"], "failed")
        self.assertEqual(modules["mod_run_failure_test_HealthyNode"]["status"], "completed")
        self.assertEqual(modules["mod_run_failure_test_DependentNode"]["status"], "skipped")

    async def test_timeout_handling(self):
        """
        Verify:
        - Evaluator exceeding its timeout is cleanly caught.
        - Result marked as error, score 0.0, status set to 'failed'.
        - Dependent evaluators are skipped.
        """
        class TimingOutNode(BaseEvaluator):
            def __init__(self):
                super().__init__("TimingOutNode", "crit_timeout", 10.0, dependencies=[], timeout_seconds=0.05)
            async def execute(self, artifact, context):
                await asyncio.sleep(0.3)
                return EvaluationResult("crit_timeout", 10.0, 10.0, 1.0, "Never reached")

        class DependentOnTimeout(BaseEvaluator):
            def __init__(self):
                super().__init__("DepOnTimeout", "crit_dep_to", 10.0, dependencies=["TimingOutNode"])
            async def execute(self, artifact, context):
                return EvaluationResult("crit_dep_to", 10.0, 10.0, 1.0, "Never reached")

        orchestrator = PipelineOrchestrator([TimingOutNode(), DependentOnTimeout()], db=self.mock_db)
        results = await orchestrator.execute_pipeline(run_id="run_to_test", artifact=self.mock_artifact)

        self.assertIn("TimingOutNode", results)
        self.assertTrue(results["TimingOutNode"].is_error)
        self.assertEqual(results["TimingOutNode"].score, 0.0)
        self.assertIn("timed out", results["TimingOutNode"].summary.lower())

        self.assertIn("DepOnTimeout", results)
        self.assertEqual(results["DepOnTimeout"].score, 0.0)
        self.assertIn("Skipped", results["DepOnTimeout"].summary)

        modules = self.mock_db.mock_modules
        self.assertEqual(modules["mod_run_to_test_TimingOutNode"]["status"], "failed")
        self.assertEqual(modules["mod_run_to_test_DepOnTimeout"]["status"], "skipped")

    # --------------------------------------------------------------------------
    # 4. Retry Behavior Tests
    # --------------------------------------------------------------------------
    async def test_retry_behavior(self):
        evaluators = get_standard_evaluators()
        orchestrator = PipelineOrchestrator(evaluators=evaluators, db=self.mock_db)

        results_1 = await orchestrator.execute_pipeline(run_id="run_retry_1", artifact=self.mock_artifact)
        self.assertEqual(len(results_1), 10)

        results_2 = await orchestrator.execute_pipeline(run_id="run_retry_1", artifact=self.mock_artifact)
        self.assertEqual(len(results_2), 10)
        for name in results_1:
            self.assertEqual(results_1[name].score, results_2[name].score)

    # --------------------------------------------------------------------------
    # 5. Result Contract & Schema Validation Tests
    # --------------------------------------------------------------------------
    def test_result_contract_validation(self):
        evaluator = ProblemAnalyzer()

        valid = EvaluationResult(
            criterion="problem_statement",
            score=8.5,
            maxScore=10.0,
            confidence=0.9,
            summary="Valid summary",
            strengths=["A"],
            weaknesses=["B"],
            recommendations=["C"],
            evidence=[EvidenceItem("source", "metric", 1, "interpretation")]
        )
        self.assertTrue(evaluator.validate(valid))

        # Invalid criterion
        self.assertFalse(evaluator.validate(EvaluationResult("wrong_crit", 8.0, 10.0, 1.0, "Summary")))
        # Score exceeds maxScore
        self.assertFalse(evaluator.validate(EvaluationResult("problem_statement", 15.0, 10.0, 1.0, "Summary")))
        # Negative score
        self.assertFalse(evaluator.validate(EvaluationResult("problem_statement", -1.0, 10.0, 1.0, "Summary")))
        # Invalid confidence
        self.assertFalse(evaluator.validate(EvaluationResult("problem_statement", 5.0, 10.0, 1.5, "Summary")))

    # --------------------------------------------------------------------------
    # 6. Full Pipeline End-to-End with all 10 Standard Evaluators
    # --------------------------------------------------------------------------
    async def test_all_standard_evaluators_execution(self):
        evaluators = get_standard_evaluators()
        orchestrator = PipelineOrchestrator(evaluators=evaluators, db=self.mock_db)

        results = await orchestrator.execute_pipeline(run_id="run_full_std_test", artifact=self.mock_artifact)

        expected = [
            "ProblemAnalyzer", "SolutionAnalyzer", "CodeQualityAnalyzer", "OptimizationAnalyzer",
            "UIAnalyzer", "PerformanceAnalyzer", "SecurityAnalyzer", "NoveltyAnalyzer",
            "DocumentationAnalyzer", "EngineeringAnalyzer"
        ]

        for name in expected:
            self.assertIn(name, results)
            res = results[name]
            self.assertGreaterEqual(res.score, 0)
            self.assertLessEqual(res.score, res.maxScore)
            self.assertGreaterEqual(res.confidence, 0.0)
            self.assertLessEqual(res.confidence, 1.0)
            self.assertGreater(len(res.summary), 0)

        total_max_score = sum(r.maxScore for r in results.values())
        self.assertEqual(total_max_score, 100.0)

        # Verify incremental DB persistence
        self.assertEqual(len(self.mock_db.mock_modules), 10)
        for mod in self.mock_db.mock_modules.values():
            self.assertIn(mod["status"], ["completed", "skipped", "failed"])
            self.assertIsNotNone(mod["started_at"])

        self.assertEqual(len(self.mock_db.mock_scores), 10)
        self.assertGreater(len(self.mock_db.mock_evidence), 0)

if __name__ == "__main__":
    unittest.main()
