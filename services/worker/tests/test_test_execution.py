import unittest
import tempfile
import shutil
import json
from pathlib import Path
import sys

# Add services/worker to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from analyzer.models import ProjectArtifact
from analyzer.evaluators.code_quality import CodeQualityAnalyzer
from analyzer.code_quality.tests_runner import analyze_tests, TestAnalysisResult

class TestRealTestExecution(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="evalforge_test_runner_")
        self.root_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    async def test_python_execution_one_passing_one_failing(self):
        """
        Fixture with one passing and one deliberately failing test.
        Assert test_failures == 1 when execution succeeds and execution_mode == 'executed'.
        """
        # Create minimal python code
        (self.root_path / "calc.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

        test_dir = self.root_path / "tests"
        test_dir.mkdir(parents=True)
        (test_dir / "test_calc.py").write_text("""
from calc import add

def test_passing_case():
    assert add(2, 3) == 5

def test_deliberately_failing_case():
    # Deliberate failure to verify empirical failure detection
    assert add(2, 3) == 999
""", encoding="utf-8")

        # 1. Direct analyze_tests call
        res = await analyze_tests(
            root_path=self.root_path,
            test_files=["tests/test_calc.py"],
            detected_languages=["Python"],
            detected_frameworks=[]
        )

        self.assertTrue(res.measurable)
        self.assertEqual(res.execution_mode, "executed")
        self.assertEqual(res.test_count, 2)
        self.assertEqual(res.test_failures, 1, "test_failures must reflect actually-failing tests (1 failure)")
        self.assertEqual(res.details.get("passed"), 1)
        self.assertEqual(res.details.get("failed"), 1)

        # 2. Integration via CodeQualityAnalyzer
        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/calc-app",
            commit_sha="abcdef123456",
            detected_languages=["Python"],
            detected_frameworks=[],
            package_managers=["pip"],
            test_files=["tests/test_calc.py"],
            config_files=[],
            file_tree=["calc.py", "tests/test_calc.py"]
        )

        analyzer = CodeQualityAnalyzer()
        eval_res = await analyzer.run_safe(artifact=artifact, context={})
        self.assertTrue(analyzer.validate(eval_res))

        # Check evidence reporting
        count_ev = next(e for e in eval_res.evidence if e.metric == "test_count")
        fail_ev = next(e for e in eval_res.evidence if e.metric == "test_failures")

        self.assertEqual(count_ev.source, "test_runner")
        self.assertEqual(count_ev.value, 2)
        self.assertIn("Executed 2 test cases", count_ev.interpretation)
        self.assertIn("1 passed, 1 failed", count_ev.interpretation)

        self.assertEqual(fail_ev.source, "test_runner")
        self.assertEqual(fail_ev.value, 1)
        self.assertIn("Recorded 1 test execution failure", fail_ev.interpretation)

    async def test_fallback_mode_reported_correctly_when_execution_fails(self):
        """
        When execution is unavailable, verify static_count fallback is labeled honestly
        and lowers the dimension's contribution to confidence.
        """
        test_dir = self.root_path / "tests"
        test_dir.mkdir(parents=True)
        # Tests that import an uninstalled dependency (which cannot run without arbitrary install)
        (test_dir / "test_fake.py").write_text("""
import non_existent_arbitrary_untrusted_pkg_98765

def test_one():
    assert True

def test_two():
    assert True
""", encoding="utf-8")

        res = await analyze_tests(
            root_path=self.root_path,
            test_files=["tests/test_fake.py"],
            detected_languages=["Python"],
            detected_frameworks=[]
        )

        # Should fall back to static count honestly
        self.assertTrue(res.measurable)
        self.assertEqual(res.execution_mode, "static_count")
        self.assertEqual(res.test_count, 2)
        self.assertIn("static inspection", res.framework)

        # Integration test through CodeQualityAnalyzer
        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/fallback-app",
            commit_sha="999888",
            detected_languages=["Python"],
            detected_frameworks=[],
            package_managers=["pip"],
            test_files=["tests/test_fake.py"],
            config_files=[],
            file_tree=["tests/test_fake.py"]
        )

        analyzer = CodeQualityAnalyzer()
        eval_res = await analyzer.run_safe(artifact=artifact, context={})

        count_ev = next(e for e in eval_res.evidence if e.metric == "test_count")
        self.assertEqual(count_ev.source, "test_discovery")
        self.assertIn("static inspection", count_ev.interpretation)
        self.assertIn("exploit", count_ev.interpretation)

    async def test_security_policy_no_untrusted_dependency_install_by_default(self):
        """
        Verify security policy: EVAL_ALLOW_DEPENDENCY_INSTALL defaults to not installing
        arbitrary untrusted packages into the environment.
        """
        from analyzer.code_quality.tests_runner import _should_install_dependencies
        # Default without env var
        self.assertFalse(_should_install_dependencies(self.root_path))

if __name__ == "__main__":
    unittest.main()
