import os
import re
import ast
import json
import logging
import subprocess
import shutil
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

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

def _scan_js_ts_heuristics(root_path: Path, js_files: List[str]) -> Tuple[int, int, List[Dict[str, Any]]]:
    """Deterministic AST & token checks for common JavaScript/TypeScript syntax and anti-patterns."""
    errors = 0
    warnings = 0
    issues = []

    # Limit scan to max 80 files to ensure fast, bounded execution
    sample_files = js_files[:80]
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

def analyze_linting_and_formatting(
    root_path: Path,
    file_tree: List[str],
    detected_languages: List[str],
    config_files: List[str]
) -> LintAnalysisResult:
    """Analyze code syntax, linting configs, and formatting across detected tech stacks."""
    is_js_ts = any(lang in ["TypeScript", "JavaScript"] for lang in detected_languages)
    is_python = "Python" in detected_languages

    if not is_js_ts and not is_python:
        # Check if project contains other source code without supported linter
        return LintAnalysisResult(
            measurable=False,
            unmeasurable_reason="Not measurable with the available submission."
        )

    total_errors = 0
    total_warnings = 0
    formatting_violations = 0
    all_issues = []
    linter_names = []
    linter_config_present = False
    formatter_config_present = False

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

        js_files = [f for f in file_tree if f.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"))]
        errors, warnings, issues = _scan_js_ts_heuristics(root_path, js_files)
        total_errors += errors
        total_warnings += warnings
        all_issues.extend(issues)
        linter_names.append("ESLint / Static Parser")

        if not formatter_config_present:
            formatting_violations += 1

    # 2. Python analysis
    if is_python:
        py_files = [f for f in file_tree if f.endswith(".py")]
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

        errors, warnings, issues = _analyze_python_syntax(root_path, py_files)
        total_errors += errors
        total_warnings += warnings
        all_issues.extend(issues)
        linter_names.append("Python AST / Ruff")

        if not has_ruff_flake8 and not is_js_ts:
            formatting_violations += 1

    return LintAnalysisResult(
        measurable=True,
        linter_name=", ".join(linter_names),
        linter_config_present=linter_config_present,
        formatter_config_present=formatter_config_present,
        errors_count=total_errors,
        warnings_count=total_warnings,
        formatting_violations_count=formatting_violations,
        issues=all_issues
    )
