import ast
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("evalforge.tests_runner")

@dataclass
class TestAnalysisResult:
    measurable: bool
    test_files_count: int = 0
    test_count: int = 0
    test_failures: int = 0
    test_suites_count: int = 0
    framework: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    unmeasurable_reason: Optional[str] = None

def _count_python_tests(root_path: Path, test_files: List[str]) -> Tuple[int, int, int]:
    """Inspect Python test files using AST to count test functions, classes, and syntax errors."""
    test_count = 0
    suites_count = 0
    failures = 0

    for rel_path in test_files:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue

        try:
            source = full_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=rel_path)
            has_tests_in_file = False

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    suites_count += 1
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith("test_") or node.name.endswith("_test"):
                        test_count += 1
                        has_tests_in_file = True

            if has_tests_in_file and suites_count == 0:
                suites_count = 1

        except SyntaxError:
            failures += 1  # Unparseable test file counts as collection failure
        except Exception:
            pass

    return test_count, suites_count, failures

def _count_js_ts_tests(root_path: Path, test_files: List[str]) -> Tuple[int, int, int]:
    """Scan JS/TS test files for test/it/describe declarations."""
    test_count = 0
    suites_count = 0
    failures = 0

    test_pattern = re.compile(r"\b(it|test)(\.(only|skip|each))?\s*\(")
    describe_pattern = re.compile(r"\bdescribe(\.(only|skip|each))?\s*\(")

    for rel_path in test_files:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue

        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            tests_in_file = len(test_pattern.findall(content))
            suites_in_file = len(describe_pattern.findall(content))

            test_count += tests_in_file
            suites_count += max(suites_in_file, 1 if tests_in_file > 0 else 0)
        except Exception:
            failures += 1

    return test_count, suites_count, failures

def _count_go_tests(root_path: Path, test_files: List[str]) -> Tuple[int, int]:
    """Scan Go test files for func Test*(t *testing.T)."""
    test_count = 0
    pattern = re.compile(r"func\s+Test\w+\s*\(")
    for rel_path in test_files:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            test_count += len(pattern.findall(content))
        except Exception:
            pass
    return test_count, len(test_files)

def _count_rust_tests(root_path: Path, test_files: List[str]) -> Tuple[int, int]:
    """Scan Rust files for #[test]."""
    test_count = 0
    pattern = re.compile(r"#\[test\]")
    for rel_path in test_files:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
            test_count += len(pattern.findall(content))
        except Exception:
            pass
    return test_count, len(test_files)

def analyze_tests(
    root_path: Path,
    test_files: List[str],
    detected_languages: List[str],
    detected_frameworks: List[str]
) -> TestAnalysisResult:
    """Deterministically analyze test coverage, test counts, and syntax validity."""
    if not test_files:
        # Check if project has no tests at all
        return TestAnalysisResult(
            measurable=True,
            test_files_count=0,
            test_count=0,
            test_failures=0,
            test_suites_count=0,
            framework=None,
            details={"status": "no_tests_found"}
        )

    # 1. Python tests
    py_test_files = [f for f in test_files if f.endswith(".py")]
    if py_test_files or "Python" in detected_languages:
        tc, sc, fails = _count_python_tests(root_path, py_test_files)
        return TestAnalysisResult(
            measurable=True,
            test_files_count=len(py_test_files),
            test_count=tc,
            test_failures=fails,
            test_suites_count=sc,
            framework="pytest / unittest",
            details={
                "collected_tests": tc,
                "test_suites": sc,
                "syntax_failures": fails
            }
        )

    # 2. JavaScript / TypeScript tests
    js_test_files = [f for f in test_files if f.endswith((".js", ".jsx", ".ts", ".tsx"))]
    if js_test_files or any(lang in ["TypeScript", "JavaScript"] for lang in detected_languages):
        tc, sc, fails = _count_js_ts_tests(root_path, js_test_files)
        fw = "Jest / Vitest" if "Next.js" in detected_frameworks or "React" in detected_frameworks else "Node Test Runner"
        return TestAnalysisResult(
            measurable=True,
            test_files_count=len(js_test_files),
            test_count=tc,
            test_failures=fails,
            test_suites_count=sc,
            framework=fw,
            details={
                "collected_tests": tc,
                "test_suites": sc,
                "syntax_failures": fails
            }
        )

    # 3. Go tests
    go_test_files = [f for f in test_files if f.endswith("_test.go")]
    if go_test_files or "Go" in detected_languages:
        tc, sc = _count_go_tests(root_path, go_test_files)
        return TestAnalysisResult(
            measurable=True,
            test_files_count=len(go_test_files),
            test_count=tc,
            test_failures=0,
            test_suites_count=sc,
            framework="go test",
            details={"collected_tests": tc}
        )

    # 4. Rust tests
    rust_test_files = [f for f in test_files if f.endswith(".rs")]
    if rust_test_files or "Rust" in detected_languages:
        tc, sc = _count_rust_tests(root_path, rust_test_files)
        return TestAnalysisResult(
            measurable=True,
            test_files_count=len(rust_test_files),
            test_count=tc,
            test_failures=0,
            test_suites_count=sc,
            framework="cargo test",
            details={"collected_tests": tc}
        )

    return TestAnalysisResult(
        measurable=False,
        unmeasurable_reason="Not measurable with the available submission."
    )
