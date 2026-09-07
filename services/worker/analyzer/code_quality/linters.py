import os
import re
import ast
import json
import logging
import asyncio
import shutil
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

from ..sandbox import IsolatedSandboxRunner

logger = logging.getLogger("evalforge.linters")

@dataclass
class LintAnalysisResult:
    measurable: bool
    linter_name: Optional[str] = None
    linter_config_present: bool = False
    formatter_config_present: bool = False
    errors_count: int = 0
    warnings_count: int = 0
    formatting_violations_count: int = 0
    issues: List[Dict[str, Any]] = field(default_factory=list)
    unmeasurable_reason: Optional[str] = None
    tool_used: str = "none"
    tool_real: bool = False
    confidence: float = 1.0


def _resolve_tool_executable(root_path: Path, local_bin_rel: str, global_name: str) -> Optional[str]:
    """
    Resolves executable path either project-local (e.g. node_modules/.bin)
    or from the current Python virtualenv or global PATH.
    """
    exts = [".cmd", ".bat", ".exe", ""] if sys.platform == "win32" else ["", ".sh"]

    # 1. Project local node_modules/.bin or local venv
    local_path = root_path / local_bin_rel
    for ext in exts:
        cand = local_path.with_name(f"{local_path.name}{ext}")
        if cand.is_file():
            return str(cand.resolve())

    # 2. Virtual environment bin/Scripts where worker runs
    venv_bin = Path(sys.executable).parent
    for ext in exts:
        cand = venv_bin / f"{global_name}{ext}"
        if cand.is_file():
            return str(cand.resolve())

    # 3. Global PATH
    which_path = shutil.which(global_name)
    if which_path:
        return which_path
    if sys.platform == "win32":
        for ext in [".cmd", ".exe", ".bat"]:
            which_cmd = shutil.which(f"{global_name}{ext}")
            if which_cmd:
                return which_cmd

    return None


async def _run_subprocess_safe(
    cmd: List[str],
    cwd: Path,
    timeout_seconds: float = 30.0
) -> Tuple[int, str, str, bool]:
    """
    Executes a tool bounded by timeout and clean sandbox environment.
    Returns (returncode, stdout, stderr, timed_out).
    """
    clean_env = IsolatedSandboxRunner().sanitize_environment()
    actual_cmd = ["cmd.exe", "/c"] + cmd if (sys.platform == "win32" and cmd and cmd[0].lower().endswith((".cmd", ".bat"))) else cmd
    try:
        proc = await asyncio.create_subprocess_exec(
            *actual_cmd,
            cwd=str(cwd),
            env=clean_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds
            )
            stdout = stdout_b.decode("utf-8", errors="replace")
            stderr = stderr_b.decode("utf-8", errors="replace")
            return (proc.returncode or 0), stdout, stderr, False
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            logger.warning(f"Subprocess {' '.join(cmd[:2])} timed out after {timeout_seconds}s")
            return -1, "", f"Timed out after {timeout_seconds}s", True
    except Exception as ex:
        logger.warning(f"Failed to launch command {' '.join(cmd[:2])}: {ex}")
        return -1, "", str(ex), False


def _scan_js_ts_heuristics(root_path: Path, js_files: List[str]) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Deterministic AST & token checks for common JavaScript/TypeScript syntax and anti-patterns."""
    errors = 0
    warnings = 0
    issues = []

    # Limit scan to max 80 files to ensure fast, bounded execution
    sample_files = [f for f in js_files if not f.startswith("node_modules/")][:80]
    for rel_path in sample_files:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue
        try:
            content = full_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            stripped = line.strip()

            # 1. Flag debugger statements
            if re.match(r"^debugger\s*;?", stripped):
                warnings += 1
                issues.append({
                    "file": rel_path,
                    "line": idx,
                    "severity": "warning",
                    "rule": "no-debugger",
                    "message": "Unexpected 'debugger' statement found in source."
                })

            # 2. Flag eval() usage
            if re.search(r"\beval\s*\(", line) and not stripped.startswith("//") and not stripped.startswith("/*"):
                warnings += 1
                issues.append({
                    "file": rel_path,
                    "line": idx,
                    "severity": "warning",
                    "rule": "no-eval",
                    "message": "eval() usage detected, presenting security and performance risks."
                })

        # 3. Balanced bracket/brace sanity check
        stack = []
        open_to_close = {'(': ')', '{': '}', '[': ']'}
        close_to_open = {')': '(', '}': '{', ']': '['}
        in_string = False
        str_char = ''

        for line_idx, line in enumerate(lines, 1):
            i = 0
            while i < len(line):
                ch = line[i]
                if not in_string:
                    if ch in ('"', "'", '`'):
                        in_string = True
                        str_char = ch
                    elif ch == '/' and i + 1 < len(line) and line[i+1] == '/':
                        break  # Line comment
                    elif ch in open_to_close:
                        stack.append((ch, line_idx))
                    elif ch in close_to_open:
                        if not stack or stack[-1][0] != close_to_open[ch]:
                            errors += 1
                            issues.append({
                                "file": rel_path,
                                "line": line_idx,
                                "severity": "error",
                                "rule": "syntax-mismatched-delimiter",
                                "message": f"Mismatched closing bracket '{ch}'."
                            })
                            break
                        else:
                            stack.pop()
                else:
                    if ch == '\\':
                        i += 1  # Skip escaped char
                    elif ch == str_char:
                        in_string = False
                i += 1
            if errors > 20:
                break

    return errors, warnings, issues


def _analyze_python_syntax(root_path: Path, py_files: List[str]) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Parse all Python files using Python's native ast.parse to detect syntax errors deterministically."""
    errors = 0
    warnings = 0
    issues = []

    for rel_path in py_files:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue

        try:
            source = full_path.read_text(encoding="utf-8", errors="ignore")
            ast.parse(source, filename=rel_path)
        except SyntaxError as se:
            errors += 1
            issues.append({
                "file": rel_path,
                "line": se.lineno or 1,
                "severity": "error",
                "rule": "python-syntax-error",
                "message": f"SyntaxError: {se.msg} (offset {se.offset})"
            })
        except IndentationError as ie:
            errors += 1
            issues.append({
                "file": rel_path,
                "line": ie.lineno or 1,
                "severity": "error",
                "rule": "python-indentation-error",
                "message": f"IndentationError: {ie.msg}"
            })
        except Exception as ex:
            warnings += 1
            issues.append({
                "file": rel_path,
                "line": 1,
                "severity": "warning",
                "rule": "python-parse-error",
                "message": str(ex)
            })

    return errors, warnings, issues


async def _scan_js_ts(
    root_path: Path,
    js_files: List[str],
    linter_config_present: bool,
    timeout_seconds: float = 30.0
) -> Tuple[int, int, List[Dict[str, Any]], str, bool, str]:
    """
    Runs ESLint if resolvable and config exists.
    Otherwise falls back to _scan_js_ts_heuristics with honest labeling.
    Returns: (errors_count, warnings_count, issues, linter_name, tool_real, tool_used)
    """
    eslint_bin = _resolve_tool_executable(root_path, "node_modules/.bin/eslint", "eslint")

    if eslint_bin and linter_config_present:
        sample_files = [f for f in js_files if not f.startswith("node_modules/")][:80]
        if not sample_files:
            return 0, 0, [], "ESLint", True, "eslint"

        cmd = [eslint_bin, "--format", "json", "--no-error-on-unmatched-pattern"] + sample_files
        code, stdout, stderr, timed_out = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)

        if not timed_out and stdout.strip():
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    errors = 0
                    warnings = 0
                    issues = []
                    for file_entry in data:
                        fp = file_entry.get("filePath", "")
                        try:
                            rel_file = str(Path(fp).relative_to(root_path))
                        except Exception:
                            rel_file = fp

                        for msg in file_entry.get("messages", []):
                            sev = msg.get("severity", 1)
                            is_err = sev == 2
                            if is_err:
                                errors += 1
                            else:
                                warnings += 1
                            issues.append({
                                "file": rel_file,
                                "line": msg.get("line", 1),
                                "severity": "error" if is_err else "warning",
                                "rule": msg.get("ruleId") or "eslint-rule",
                                "message": msg.get("message", "")
                            })
                    return errors, warnings, issues, "ESLint", True, "eslint"
            except Exception as ex:
                logger.warning(f"Failed to parse ESLint JSON output: {ex}")

    errors, warnings, issues = _scan_js_ts_heuristics(root_path, js_files)
    label = "Heuristic Parser (ESLint unavailable)" if not eslint_bin else "Heuristic Parser (No ESLint config)"
    return errors, warnings, issues, label, False, "heuristic"


async def _scan_python(
    root_path: Path,
    py_files: List[str],
    has_ruff_flake8: bool,
    timeout_seconds: float = 30.0
) -> Tuple[int, int, List[Dict[str, Any]], str, bool, str]:
    """
    Runs Ruff if resolvable, else Flake8.
    Otherwise falls back to _analyze_python_syntax (AST parse) with honest labeling.
    Returns: (errors_count, warnings_count, issues, linter_name, tool_real, tool_used)
    """
    ruff_bin = _resolve_tool_executable(root_path, ".venv/Scripts/ruff", "ruff")
    sample_files = [f for f in py_files if not f.startswith((".venv/", "venv/"))][:80]
    if not sample_files:
        return 0, 0, [], "Ruff" if ruff_bin else "Python AST (No files)", bool(ruff_bin), "ruff" if ruff_bin else "ast.parse"

    if ruff_bin:
        cmd = [ruff_bin, "check", "--output-format", "json"] + sample_files
        code, stdout, stderr, timed_out = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)
        if not timed_out:
            try:
                data = json.loads(stdout)
                if isinstance(data, list):
                    errors = 0
                    warnings = 0
                    issues = []
                    for diag in data:
                        code_str = diag.get("code", "")
                        # Critical syntax errors and undefined symbols are errors
                        is_err = code_str.startswith(("E9", "F82", "F7", "Syntax")) or diag.get("severity") == "error" and not code_str.startswith("I")
                        if is_err:
                            errors += 1
                        else:
                            warnings += 1
                        loc = diag.get("location", {})
                        fn = diag.get("filename", "")
                        try:
                            rel_fn = str(Path(fn).relative_to(root_path))
                        except Exception:
                            rel_fn = fn
                        issues.append({
                            "file": rel_fn,
                            "line": loc.get("row", 1),
                            "severity": "error" if is_err else "warning",
                            "rule": code_str,
                            "message": diag.get("message", "")
                        })
                    return errors, warnings, issues, "Ruff", True, "ruff"
            except Exception as ex:
                logger.warning(f"Failed to parse Ruff JSON output: {ex}")

    flake8_bin = _resolve_tool_executable(root_path, ".venv/Scripts/flake8", "flake8")
    if flake8_bin:
        cmd = [flake8_bin, "--format", "json"] + sample_files
        code, stdout, stderr, timed_out = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)
        if not timed_out and stdout.strip():
            try:
                data = json.loads(stdout)
                if isinstance(data, dict):
                    errors = 0
                    warnings = 0
                    issues = []
                    for fn, msgs in data.items():
                        try:
                            rel_fn = str(Path(fn).relative_to(root_path))
                        except Exception:
                            rel_fn = fn
                        for msg in msgs:
                            code_str = msg.get("code", "")
                            is_err = code_str.startswith(("E9", "F82"))
                            if is_err:
                                errors += 1
                            else:
                                warnings += 1
                            issues.append({
                                "file": rel_fn,
                                "line": msg.get("line_number", 1),
                                "severity": "error" if is_err else "warning",
                                "rule": code_str,
                                "message": msg.get("text", "")
                            })
                    return errors, warnings, issues, "Flake8", True, "flake8"
            except Exception:
                pass

    errors, warnings, issues = _analyze_python_syntax(root_path, py_files)
    label = "Python AST (Ruff/Flake8 unavailable)"
    return errors, warnings, issues, label, False, "ast.parse"


async def _check_formatting(
    root_path: Path,
    is_js_ts: bool,
    is_python: bool,
    js_files: List[str],
    py_files: List[str],
    formatter_config_present: bool,
    timeout_seconds: float = 30.0
) -> int:
    """
    Runs prettier --check / black --check / ruff format --check.
    Returns real count of files with formatting violations.
    """
    violations = 0

    if is_js_ts:
        prettier_bin = _resolve_tool_executable(root_path, "node_modules/.bin/prettier", "prettier")
        if prettier_bin:
            sample_js = [f for f in js_files if not f.startswith("node_modules/")][:80]
            if sample_js:
                cmd = [prettier_bin, "--check"] + sample_js
                code, stdout, stderr, _ = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)
                lines = (stdout + "\n" + stderr).splitlines()
                warn_files = [line for line in lines if line.strip().startswith("[warn]") and "Code style issues found" not in line]
                if warn_files:
                    violations += len(warn_files)
                elif code != 0:
                    violations += 1
        elif not formatter_config_present:
            violations += 1

    if is_python:
        ruff_bin = _resolve_tool_executable(root_path, ".venv/Scripts/ruff", "ruff")
        black_bin = _resolve_tool_executable(root_path, ".venv/Scripts/black", "black")
        sample_py = [f for f in py_files if not f.startswith((".venv/", "venv/"))][:80]

        if ruff_bin and sample_py:
            cmd = [ruff_bin, "format", "--check"] + sample_py
            code, stdout, stderr, _ = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)
            out = stdout + "\n" + stderr
            m = re.search(r"(\d+)\s+file[s]?\s+would\s+be\s+reformatted", out)
            if m:
                violations += int(m.group(1))
            elif code != 0:
                violations += 1
        elif black_bin and sample_py:
            cmd = [black_bin, "--check"] + sample_py
            code, stdout, stderr, _ = await _run_subprocess_safe(cmd, cwd=root_path, timeout_seconds=timeout_seconds)
            out = stdout + "\n" + stderr
            m = re.search(r"(\d+)\s+file[s]?\s+would\s+be\s+reformatted", out)
            if m:
                violations += int(m.group(1))
            elif code != 0:
                violations += 1
        elif not formatter_config_present and not is_js_ts:
            violations += 1

    return violations


async def analyze_linting_and_formatting(
    root_path: Path,
    file_tree: List[str],
    detected_languages: List[str],
    config_files: List[str],
    timeout_seconds: float = 30.0
) -> LintAnalysisResult:
    """Analyze code syntax, linting configs, and formatting across detected tech stacks."""
    is_js_ts = any(lang in ["TypeScript", "JavaScript"] for lang in detected_languages)
    is_python = "Python" in detected_languages

    if not is_js_ts and not is_python:
        return LintAnalysisResult(
            measurable=False,
            unmeasurable_reason="Not measurable with the available submission."
        )

    total_errors = 0
    total_warnings = 0
    all_issues = []
    linter_names = []
    tools_used = []
    real_tools_status = []
    linter_config_present = False
    formatter_config_present = False

    js_files = [f for f in file_tree if f.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))]
    py_files = [f for f in file_tree if f.endswith(".py")]

    # 1. JavaScript / TypeScript analysis
    if is_js_ts:
        eslint_configs = [c for c in config_files if "eslint" in c.lower()]
        pkg_json = root_path / "package.json"
        has_pkg_eslint = False
        has_pkg_prettier = False

        if pkg_json.exists():
            try:
                pkg_data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                if "eslintConfig" in pkg_data or "eslint" in pkg_data.get("devDependencies", {}) or "eslint" in pkg_data.get("dependencies", {}):
                    has_pkg_eslint = True
                if "prettier" in pkg_data or "prettier" in pkg_data.get("devDependencies", {}):
                    has_pkg_prettier = True
            except Exception:
                pass

        if bool(eslint_configs) or has_pkg_eslint:
            linter_config_present = True

        prettier_configs = [f for f in file_tree if any(p in f.lower() for p in [".prettierrc", "prettier.config"])]
        if bool(prettier_configs) or has_pkg_prettier:
            formatter_config_present = True

        errors, warnings, issues, linter_name, tool_real, tool_used = await _scan_js_ts(
            root_path=root_path,
            js_files=js_files,
            linter_config_present=linter_config_present,
            timeout_seconds=timeout_seconds
        )
        total_errors += errors
        total_warnings += warnings
        all_issues.extend(issues)
        linter_names.append(linter_name)
        tools_used.append(tool_used)
        real_tools_status.append(tool_real)

    # 2. Python analysis
    if is_python:
        has_ruff_flake8 = any(
            c in ["pyproject.toml", "setup.cfg", ".flake8", "ruff.toml", ".ruff.toml"]
            for c in config_files
        )
        pyproject = root_path / "pyproject.toml"
        if pyproject.exists():
            try:
                txt = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
                if "[tool.ruff]" in txt or "[tool.black]" in txt or "[tool.flake8]" in txt:
                    has_ruff_flake8 = True
            except Exception:
                pass

        if has_ruff_flake8:
            linter_config_present = True
            formatter_config_present = True

        py_errors, py_warnings, py_issues, py_linter_name, py_tool_real, py_tool_used = await _scan_python(
            root_path=root_path,
            py_files=py_files,
            has_ruff_flake8=has_ruff_flake8,
            timeout_seconds=timeout_seconds
        )
        total_errors += py_errors
        total_warnings += py_warnings
        all_issues.extend(py_issues)
        linter_names.append(py_linter_name)
        tools_used.append(py_tool_used)
        real_tools_status.append(py_tool_real)

    # 3. Formatting violations check
    formatting_violations = await _check_formatting(
        root_path=root_path,
        is_js_ts=is_js_ts,
        is_python=is_python,
        js_files=js_files,
        py_files=py_files,
        formatter_config_present=formatter_config_present,
        timeout_seconds=timeout_seconds
    )

    all_real = all(real_tools_status) if real_tools_status else False
    confidence = 1.0 if all_real else 0.6

    return LintAnalysisResult(
        measurable=True,
        linter_name=", ".join(linter_names),
        linter_config_present=linter_config_present,
        formatter_config_present=formatter_config_present,
        errors_count=total_errors,
        warnings_count=total_warnings,
        formatting_violations_count=formatting_violations,
        issues=all_issues,
        tool_used=", ".join(tools_used),
        tool_real=all_real,
        confidence=confidence
    )
