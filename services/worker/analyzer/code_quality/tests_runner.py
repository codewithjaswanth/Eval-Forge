import ast
import re
import os
import sys
import json
import logging
import asyncio
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from ..sandbox import IsolatedSandboxRunner
from .linters import _resolve_tool_executable, _run_subprocess_safe

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
    execution_mode: str = "static_count"  # "executed" | "static_count"

TestAnalysisResult.__test__ = False


def _should_install_dependencies(root_path: Path) -> bool:
    """
    Security check: Untrusted third-party dependencies are NEVER installed by default.
    Only permitted if EVAL_ALLOW_DEPENDENCY_INSTALL=true (or EVALFORGE_ALLOW_DEPENDENCY_INSTALL=true)
    AND a committed lockfile is present.
    """
    allow = (
        os.environ.get("EVAL_ALLOW_DEPENDENCY_INSTALL", "").lower() in ("true", "1") or
        os.environ.get("EVALFORGE_ALLOW_DEPENDENCY_INSTALL", "").lower() in ("true", "1")
    )
    if not allow:
        return False
    lockfiles = ["poetry.lock", "Pipfile.lock", "requirements.txt", "package-lock.json", "pnpm-lock.yaml", "yarn.lock"]
    return any((root_path / lf).is_file() for lf in lockfiles)

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

async def _execute_python_tests(
    root_path: Path,
    py_test_files: List[str],
    timeout_seconds: float = 30.0
) -> Optional[TestAnalysisResult]:
    """
    Attempt actual execution inside the sandbox, with a timeout:
    pytest -q --tb=no --json-report --json-report-file=<tmp>
    Parses real pass/fail/error counts from structured output.
    """
    # Security decision: do not install untrusted third-party dependencies by default.
    allow_install = (
        os.environ.get("EVAL_ALLOW_DEPENDENCY_INSTALL", "").lower() in ("true", "1") or
        os.environ.get("EVALFORGE_ALLOW_DEPENDENCY_INSTALL", "").lower() in ("true", "1")
    )
    # If EVAL_ALLOW_DEPENDENCY_INSTALL is set and lockfile exists, dependencies can be used,
    # but by default we never perform arbitrary untrusted installations.

    pytest_bin = _resolve_tool_executable(root_path, ".venv/Scripts/pytest", "pytest")
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        report_file = Path(tmp_dir) / "pytest_report.json"
        
        if pytest_bin:
            cmd = [pytest_bin, "-q", "--tb=no", "--json-report", f"--json-report-file={report_file}"]
        else:
            cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", "--json-report", f"--json-report-file={report_file}"]

        if py_test_files:
            cmd.extend([str(root_path / f) for f in py_test_files[:30]])
        else:
            cmd.append(str(root_path))

        clean_env = IsolatedSandboxRunner().sanitize_environment()
        clean_env["PYTHONPATH"] = str(root_path.resolve())
        
        actual_cmd = ["cmd.exe", "/c"] + cmd if (sys.platform == "win32" and cmd and cmd[0].lower().endswith((".cmd", ".bat"))) else cmd
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *actual_cmd,
                cwd=str(root_path),
                env=clean_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                stdout = stdout_b.decode("utf-8", errors="replace")
                stderr = stderr_b.decode("utf-8", errors="replace")
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except Exception:
                    pass
                logger.warning(f"Python pytest execution timed out after {timeout_seconds}s")
                return None
        except Exception as e:
            logger.warning(f"Could not launch pytest process: {e}")
            return None

        # 1. Parse structured json report if generated
        if report_file.exists():
            try:
                data = json.loads(report_file.read_text(encoding="utf-8", errors="ignore"))
                summary = data.get("summary", {})
                passed = summary.get("passed", 0)
                failed = summary.get("failed", 0)
                errors = summary.get("error", 0)
                collected = summary.get("collected", 0)
                total = summary.get("total", passed + failed + errors)
                test_count = max(total, collected)
                
                # Tests must have actually executed (at least one pass or fail)
                # If only collection/import errors occurred (0 run), fall back to static count
                if (passed + failed) > 0:
                    return TestAnalysisResult(
                        measurable=True,
                        test_files_count=len(py_test_files),
                        test_count=passed + failed,
                        test_failures=failed,
                        test_suites_count=len(py_test_files) or 1,
                        framework="pytest",
                        execution_mode="executed",
                        details={
                            "passed": passed,
                            "failed": failed,
                            "errors": errors,
                            "total": passed + failed,
                            "execution_mode": "executed",
                            "stdout_snippet": stdout[:400] if stdout else ""
                        }
                    )
            except Exception as ex:
                logger.warning(f"Failed to parse pytest json-report file: {ex}")

        # 2. Fallback parse pytest text summary from stdout
        m_pass = re.search(r"(\d+)\s+passed", stdout)
        m_fail = re.search(r"(\d+)\s+failed", stdout)
        m_err = re.search(r"(\d+)\s+error[s]?", stdout)
        if m_pass or m_fail or m_err:
            passed = int(m_pass.group(1)) if m_pass else 0
            failed = int(m_fail.group(1)) if m_fail else 0
            errors = int(m_err.group(1)) if m_err else 0
            if (passed + failed) > 0:
                return TestAnalysisResult(
                    measurable=True,
                    test_files_count=len(py_test_files),
                    test_count=passed + failed,
                    test_failures=failed,
                    test_suites_count=len(py_test_files) or 1,
                    framework="pytest",
                    execution_mode="executed",
                    details={
                        "passed": passed,
                        "failed": failed,
                        "errors": errors,
                        "total": passed + failed,
                        "execution_mode": "executed"
                    }
                )

    return None


async def _execute_js_tests(
    root_path: Path,
    js_test_files: List[str],
    timeout_seconds: float = 30.0
) -> Optional[TestAnalysisResult]:
    """
    Attempt actual execution of JS/TS tests inside the sandbox.
    Only runs when a test script is declared in package.json.
    """
    pkg_path = root_path / "package.json"
    if not pkg_path.is_file():
        return None

    try:
        pkg_data = json.loads(pkg_path.read_text(encoding="utf-8", errors="ignore"))
        scripts = pkg_data.get("scripts", {})
        test_script = scripts.get("test", "")
        if not test_script or "no test specified" in test_script:
            return None
    except Exception:
        return None

    sandbox = IsolatedSandboxRunner()
    allow_host = os.environ.get("EVALFORGE_ALLOW_HOST_TEST_EXECUTION", "").lower() in ("true", "1")
    if not sandbox.container_runtime and not allow_host:
        logger.info(
            "[Security] Host execution of untrusted JS package scripts is disabled without container isolation. "
            "Falling back to static AST test analysis."
        )
        return None

    if sandbox.container_runtime:
        from ..sandbox import SandboxLimits
        limits = SandboxLimits(timeout_seconds=timeout_seconds, network_enabled=False)
        cmd = ["npm", "test", "--", "--ci"]
        result = sandbox.execute(root_path, cmd, limits=limits, allow_host_fallback=False)
        if result.timed_out:
            return None
        combined_output = result.stdout + "\n" + result.stderr
    else:
        # Controlled host test execution (only when EVALFORGE_ALLOW_HOST_TEST_EXECUTION=true)
        npm_bin = _resolve_tool_executable(root_path, "", "npm")
        if not npm_bin:
            return None
        cmd = [npm_bin, "test", "--", "--ci"]
        code, stdout, stderr, timed_out = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)
        if timed_out:
            return None
        combined_output = stdout + "\n" + stderr
    # 1. Parse Jest JSON format
    for marker in ['{"numFailedTestSuites":', '{"numFailedTests":', '{"numPassedTests":']:
        idx = combined_output.find(marker)
        if idx != -1:
            try:
                json_str = combined_output[idx:].strip()
                data = json.loads(json_str)
                total = data.get("numTotalTests", 0)
                failed = data.get("numFailedTests", 0)
                passed = data.get("numPassedTests", 0)
                if total > 0:
                    return TestAnalysisResult(
                        measurable=True,
                        test_files_count=len(js_test_files),
                        test_count=total,
                        test_failures=failed,
                        test_suites_count=data.get("numTotalTestSuites", len(js_test_files)),
                        framework="Jest",
                        execution_mode="executed",
                        details={
                            "passed": passed,
                            "failed": failed,
                            "total": total,
                            "execution_mode": "executed"
                        }
                    )
            except Exception:
                pass

    # 2. Parse Mocha / generic test runner summary
    m_pass = re.search(r"(\d+)\s+passing", combined_output)
    m_fail = re.search(r"(\d+)\s+failing", combined_output)
    if m_pass or m_fail:
        passed = int(m_pass.group(1)) if m_pass else 0
        failed = int(m_fail.group(1)) if m_fail else 0
        total = passed + failed
        if total > 0:
            return TestAnalysisResult(
                measurable=True,
                test_files_count=len(js_test_files),
                test_count=total,
                test_failures=failed,
                test_suites_count=len(js_test_files) or 1,
                framework="npm test",
                execution_mode="executed",
                details={
                    "passed": passed,
                    "failed": failed,
                    "total": total,
                    "execution_mode": "executed"
                }
            )

    return None


async def analyze_tests(
    root_path: Path,
    test_files: List[str],
    detected_languages: List[str],
    detected_frameworks: List[str],
    timeout_seconds: float = 30.0
) -> TestAnalysisResult:
    """
    Deterministically analyze test suites.
    Attempts actual execution inside the sandbox with timeout.
    Falls back to static AST / regex parsing when execution cannot run,
    labeling execution_mode honestly to mitigate the 'submit 50 tests that parse but never run' exploit.
    """
    if not test_files:
        return TestAnalysisResult(
            measurable=True,
            test_files_count=0,
            test_count=0,
            test_failures=0,
            test_suites_count=0,
            framework=None,
            execution_mode="static_count",
            details={"status": "no_tests_found"}
        )

    # 1. Python tests
    py_test_files = [f for f in test_files if f.endswith(".py")]
    if py_test_files or "Python" in detected_languages:
        exec_res = await _execute_python_tests(root_path, py_test_files, timeout_seconds=timeout_seconds)
        if exec_res is not None:
            return exec_res

        tc, sc, fails = _count_python_tests(root_path, py_test_files)
        return TestAnalysisResult(
            measurable=True,
            test_files_count=len(py_test_files),
            test_count=tc,
            test_failures=fails,
            test_suites_count=sc,
            framework="pytest / unittest (static inspection)",
            execution_mode="static_count",
            details={
                "collected_tests": tc,
                "test_suites": sc,
                "syntax_failures": fails,
                "execution_mode": "static_count",
                "fallback_reason": "Execution unavailable or dependencies not installed by default"
            }
        )

    # 2. JavaScript / TypeScript tests
    js_test_files = [f for f in test_files if f.endswith((".js", ".jsx", ".ts", ".tsx"))]
    if js_test_files or any(lang in ["TypeScript", "JavaScript"] for lang in detected_languages):
        exec_res = await _execute_js_tests(root_path, js_test_files, timeout_seconds=timeout_seconds)
        if exec_res is not None:
            return exec_res

        tc, sc, fails = _count_js_ts_tests(root_path, js_test_files)
        fw = "Jest / Vitest (static inspection)" if "Next.js" in detected_frameworks or "React" in detected_frameworks else "Node Test Runner (static inspection)"
        return TestAnalysisResult(
            measurable=True,
            test_files_count=len(js_test_files),
            test_count=tc,
            test_failures=fails,
            test_suites_count=sc,
            framework=fw,
            execution_mode="static_count",
            details={
                "collected_tests": tc,
                "test_suites": sc,
                "syntax_failures": fails,
                "execution_mode": "static_count",
                "fallback_reason": "Execution unavailable or test script unconfigured"
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
            framework="go test (static inspection)",
            execution_mode="static_count",
            details={"collected_tests": tc, "execution_mode": "static_count"}
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
            framework="cargo test (static inspection)",
            execution_mode="static_count",
            details={"collected_tests": tc, "execution_mode": "static_count"}
        )

    return TestAnalysisResult(
        measurable=False,
        unmeasurable_reason="Not measurable with the available submission."
    )
