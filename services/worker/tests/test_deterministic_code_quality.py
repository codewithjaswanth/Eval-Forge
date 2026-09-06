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
from analyzer.evaluators.base import EvaluationResult, EvidenceItem

class TestDeterministicCodeQuality(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="evalforge_test_cq_")
        self.root_path = Path(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # --------------------------------------------------------------------------
    # 1. TypeScript / Next.js Project Test
    # --------------------------------------------------------------------------
    async def test_typescript_nextjs_project(self):
        # Create package.json
        pkg_data = {
            "name": "sample-next-app",
            "version": "1.0.0",
            "license": "MIT",
            "scripts": {
                "dev": "next dev",
                "build": "next build",
                "test": "jest"
            },
            "dependencies": {
                "next": "15.0.0",
                "react": "19.0.0"
            },
            "devDependencies": {
                "typescript": "^5.0.0",
                "eslint": "^9.0.0",
                "jest": "^29.0.0"
            }
        }
        (self.root_path / "package.json").write_text(json.dumps(pkg_data, indent=2))
        (self.root_path / "package-lock.json").write_text("{}")
        (self.root_path / "eslint.config.js").write_text("export default [];")

        # Create tsconfig.json with strict: true
        tsconfig = {
            "compilerOptions": {
                "target": "ES2022",
                "strict": True,
                "noImplicitAny": True
            }
        }
        (self.root_path / "tsconfig.json").write_text(json.dumps(tsconfig, indent=2))

        # Create source files
        src_dir = self.root_path / "src"
        src_dir.mkdir(parents=True)
        (src_dir / "index.ts").write_text("export function add(a: number, b: number): number { return a + b; }")
        (src_dir / "utils.ts").write_text("import { add } from './index'; export const sum = add(1, 2);")

        # Create test file
        test_dir = self.root_path / "tests"
        test_dir.mkdir(parents=True)
        (test_dir / "index.test.ts").write_text("""
describe('add tests', () => {
    it('adds numbers correctly', () => {
        expect(1 + 1).toBe(2);
    });
    test('handles zero', () => {
        expect(0 + 0).toBe(0);
    });
});
""")

        file_tree = [
            "package.json", "package-lock.json", "eslint.config.js", "tsconfig.json",
            "src/index.ts", "src/utils.ts", "tests/index.test.ts"
        ]

        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/sample-app",
            commit_sha="abcdef123456",
            detected_languages=["TypeScript", "JavaScript"],
            detected_frameworks=["Next.js", "React"],
            package_managers=["npm"],
            has_frontend=True,
            has_backend=True,
            test_files=["tests/index.test.ts"],
            config_files=["package.json", "tsconfig.json", "eslint.config.js"],
            file_tree=file_tree
        )

        analyzer = CodeQualityAnalyzer()
        result = await analyzer.run_safe(artifact=artifact, context={})

        self.assertTrue(analyzer.validate(result))
        self.assertEqual(result.criterion, "code_quality")
        self.assertGreaterEqual(result.score, 12.0)
        self.assertEqual(result.confidence, 1.0)  # All 5 dimensions measured

        # Check evidence metrics
        metrics = {e.metric: e.value for e in result.evidence}
        self.assertEqual(metrics["lint_errors"], 0)
        self.assertEqual(metrics["type_errors"], 0)
        self.assertEqual(metrics["test_count"], 2)
        self.assertEqual(metrics["test_failures"], 0)
        self.assertEqual(metrics["source_file_count"], 4)  # eslint.config.js + src/index.ts + src/utils.ts + tests/index.test.ts
        self.assertEqual(metrics["suspicious_project_structure_issues"], 0)

    # --------------------------------------------------------------------------
    # 2. Python Project Test
    # --------------------------------------------------------------------------
    async def test_python_project(self):
        pyproject = """
[project]
name = "sample-python-app"
version = "0.1.0"
dependencies = [
    "fastapi>=0.110.0",
    "pydantic>=2.0.0"
]

[tool.ruff]
line-length = 100
"""
        (self.root_path / "pyproject.toml").write_text(pyproject)
        (self.root_path / "requirements.txt").write_text("fastapi==0.110.0\npydantic==2.6.0\n")

        # Create source files with type annotations
        (self.root_path / "main.py").write_text("""
def calculate_total(price: float, tax: float) -> float:
    return price + tax

def format_name(first: str, last: str) -> str:
    return f"{first} {last}"
""")

        # Create test file
        test_dir = self.root_path / "tests"
        test_dir.mkdir(parents=True)
        (test_dir / "test_main.py").write_text("""
from main import calculate_total

def test_calculate_total():
    assert calculate_total(10.0, 1.0) == 11.0

def test_zero():
    assert calculate_total(0.0, 0.0) == 0.0
""")

        file_tree = ["pyproject.toml", "requirements.txt", "main.py", "tests/test_main.py"]

        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/sample-python",
            commit_sha="123456abcdef",
            detected_languages=["Python"],
            detected_frameworks=["FastAPI"],
            package_managers=["pip"],
            has_backend=True,
            test_files=["tests/test_main.py"],
            config_files=["pyproject.toml", "requirements.txt"],
            file_tree=file_tree
        )

        analyzer = CodeQualityAnalyzer()
        result = await analyzer.run_safe(artifact=artifact, context={})

        self.assertTrue(analyzer.validate(result))
        self.assertEqual(result.criterion, "code_quality")
        self.assertGreaterEqual(result.score, 12.0)
        self.assertEqual(result.confidence, 1.0)

        metrics = {e.metric: e.value for e in result.evidence}
        self.assertEqual(metrics["lint_errors"], 0)
        self.assertEqual(metrics["test_count"], 2)
        self.assertEqual(metrics["test_failures"], 0)
        self.assertEqual(metrics["source_file_count"], 2)

    # --------------------------------------------------------------------------
    # 3. Non-JS / Unsupported Dimensions Test
    # --------------------------------------------------------------------------
    async def test_unsupported_dimensions_do_not_award_points(self):
        # Plain markdown/text project with no supported programming languages
        (self.root_path / "README.md").write_text("# Plain Documentation Project")

        file_tree = ["README.md"]

        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/docs-only",
            commit_sha="999999",
            detected_languages=[],
            detected_frameworks=[],
            package_managers=[],
            test_files=[],
            config_files=[],
            file_tree=file_tree
        )

        analyzer = CodeQualityAnalyzer()
        result = await analyzer.run_safe(artifact=artifact, context={})

        self.assertTrue(analyzer.validate(result))
        # Unmeasurable dimensions must produce unmeasurable evidence
        unmeasurable_items = [e for e in result.evidence if e.interpretation == "Not measurable with the available submission."]
        self.assertGreater(len(unmeasurable_items), 0)

        # Confirm score does NOT receive points for missing measurements
        self.assertLessEqual(result.score, 3.0)
        # Confidence should be low because most dimensions were unmeasurable
        self.assertLessEqual(result.confidence, 0.40)

    # --------------------------------------------------------------------------
    # 4. Messy Project with Committed Binaries & Syntax Errors
    # --------------------------------------------------------------------------
    async def test_messy_project_penalties(self):
        # Committed executable binary
        (self.root_path / "hack.exe").write_bytes(b"\x00\x01\x02")
        
        # Committed node_modules
        nm_dir = self.root_path / "node_modules" / "some-pkg"
        nm_dir.mkdir(parents=True)
        (nm_dir / "index.js").write_text("module.exports = {};")

        # Empty source file
        (self.root_path / "empty.ts").write_text("")

        # Broken Python file with SyntaxError
        (self.root_path / "broken.py").write_text("def broken_syntax( :\n    return 42\n")

        file_tree = ["hack.exe", "node_modules/some-pkg/index.js", "empty.ts", "broken.py"]

        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/messy",
            commit_sha="666666",
            detected_languages=["Python", "TypeScript"],
            detected_frameworks=[],
            package_managers=[],
            test_files=[],
            config_files=[],
            file_tree=file_tree
        )

        analyzer = CodeQualityAnalyzer()
        result = await analyzer.run_safe(artifact=artifact, context={})

        self.assertTrue(analyzer.validate(result))

        # Check that suspicious issues and syntax errors were caught
        metrics = {e.metric: e.value for e in result.evidence}
        self.assertGreater(metrics["lint_errors"], 0)
        self.assertGreater(metrics["suspicious_project_structure_issues"], 0)

        # Score should be heavily penalized
        self.assertLess(result.score, 6.0)

        # Weaknesses should cite the detected problems
        weaknesses_str = " ".join(result.weaknesses)
        self.assertIn(".exe", weaknesses_str)
        self.assertIn("node_modules", weaknesses_str)

    # --------------------------------------------------------------------------
    # 5. Contract Conformance
    # --------------------------------------------------------------------------
    async def test_contract_conformance(self):
        (self.root_path / "index.js").write_text("console.log('hello');")
        artifact = ProjectArtifact(
            root_path=self.root_path,
            source_type="test_fixture",
            repository_url="https://github.com/test-org/contract-test",
            commit_sha="777777",
            detected_languages=["JavaScript"],
            detected_frameworks=[],
            package_managers=[],
            test_files=[],
            config_files=[],
            file_tree=["index.js"]
        )

        analyzer = CodeQualityAnalyzer()
        result = await analyzer.run_safe(artifact=artifact, context={})
        d = result.to_dict()

        expected_keys = [
            "criterion", "score", "maxScore", "confidence", "summary",
            "strengths", "weaknesses", "recommendations", "evidence"
        ]
        for k in expected_keys:
            self.assertIn(k, d)

        self.assertIsInstance(d["evidence"], list)
        for ev in d["evidence"]:
            self.assertIn("source", ev)
            self.assertIn("metric", ev)
            self.assertIn("value", ev)
            self.assertIn("interpretation", ev)
            self.assertIn("timestamp", ev)

if __name__ == "__main__":
    unittest.main()
