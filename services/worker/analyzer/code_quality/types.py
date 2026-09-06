import ast
import json
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("evalforge.types")

@dataclass
class TypeSafetyResult:
    measurable: bool
    type_system: str
    strict_mode: bool = False
    type_errors_count: int = 0
    type_coverage_ratio: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)
    unmeasurable_reason: Optional[str] = None

def _strip_json_comments_and_trailing_commas(text: str) -> str:
    """Strip single-line and multi-line comments and trailing commas from JSON strings."""
    # Remove single line comments // ...
    text = re.sub(r"//.*", "", text)
    # Remove multi-line comments /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    # Remove trailing commas before } or ]
    text = re.sub(r",\s*([\]}])", r"\1", text)
    return text

def _parse_tsconfig(tsconfig_path: Path) -> Dict[str, Any]:
    """Safely parse tsconfig.json handling comments and relaxed syntax."""
    try:
        raw = tsconfig_path.read_text(encoding="utf-8", errors="ignore")
        clean = _strip_json_comments_and_trailing_commas(raw)
        return json.loads(clean)
    except Exception as e:
        logger.warning(f"Failed to parse tsconfig at {tsconfig_path}: {e}")
        return {}

def _analyze_python_type_annotations(root_path: Path, py_files: List[str]) -> Tuple[int, int]:
    """Calculate ratio of type-annotated functions across Python source files."""
    total_funcs = 0
    annotated_funcs = 0

    for rel_path in py_files[:100]:
        full_path = root_path / rel_path
        if not full_path.is_file():
            continue

        try:
            source = full_path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_funcs += 1
                    has_arg_annotation = any(arg.annotation is not None for arg in node.args.args if arg.arg != "self" and arg.arg != "cls")
                    has_ret_annotation = node.returns is not None
                    if has_arg_annotation or has_ret_annotation:
                        annotated_funcs += 1
        except Exception:
            continue

    return annotated_funcs, total_funcs

def analyze_type_safety(
    root_path: Path,
    file_tree: List[str],
    detected_languages: List[str],
    config_files: List[str]
) -> TypeSafetyResult:
    """Analyze static type safety, compiler options, and type annotation completeness."""
    # 1. TypeScript Check
    if "TypeScript" in detected_languages or any("tsconfig" in c for c in config_files):
        tsconfig_path = root_path / "tsconfig.json"
        strict_mode = False
        compiler_opts = {}

        if tsconfig_path.exists():
            cfg = _parse_tsconfig(tsconfig_path)
            compiler_opts = cfg.get("compilerOptions", {})
            strict_mode = bool(compiler_opts.get("strict", False))

        ts_files_count = len([f for f in file_tree if f.endswith((".ts", ".tsx"))])
        js_files_count = len([f for f in file_tree if f.endswith((".js", ".jsx"))])
        total_code_files = ts_files_count + js_files_count

        coverage = round(ts_files_count / max(total_code_files, 1), 3)

        return TypeSafetyResult(
            measurable=True,
            type_system="TypeScript",
            strict_mode=strict_mode,
            type_errors_count=0,
            type_coverage_ratio=coverage,
            details={
                "ts_files": ts_files_count,
                "js_files": js_files_count,
                "strict_compiler_option": strict_mode,
                "compiler_options": {
                    k: compiler_opts[k] for k in ["strict", "noImplicitAny", "target", "module"] if k in compiler_opts
                }
            }
        )

    # 2. Python Check
    if "Python" in detected_languages:
        py_files = [f for f in file_tree if f.endswith(".py")]
        annotated, total = _analyze_python_type_annotations(root_path, py_files)
        ratio = round(annotated / max(total, 1), 3) if total > 0 else 0.0

        has_mypy = any(c in ["mypy.ini", ".mypy.ini"] for c in config_files)
        pyproject = root_path / "pyproject.toml"
        if pyproject.exists():
            try:
                if "[tool.mypy]" in pyproject.read_text(encoding="utf-8", errors="ignore"):
                    has_mypy = True
            except Exception:
                pass

        return TypeSafetyResult(
            measurable=True,
            type_system="Python Type Hints",
            strict_mode=has_mypy,
            type_errors_count=0,
            type_coverage_ratio=ratio,
            details={
                "annotated_functions": annotated,
                "total_functions": total,
                "mypy_configured": has_mypy
            }
        )

    # 3. Compiled Static Languages (Go, Rust, Java, C#, C++)
    for lang in ["Go", "Rust", "Java", "C#", "C++"]:
        if lang in detected_languages:
            return TypeSafetyResult(
                measurable=True,
                type_system=f"{lang} Static Type System",
                strict_mode=True,
                type_errors_count=0,
                type_coverage_ratio=1.0,
                details={"native_static_typing": True}
            )

    # 4. Pure JavaScript (no TypeScript)
    if "JavaScript" in detected_languages:
        return TypeSafetyResult(
            measurable=True,
            type_system="JavaScript (Untyped)",
            strict_mode=False,
            type_errors_count=0,
            type_coverage_ratio=0.0,
            details={"warning": "Dynamic typing without compile-time static type verification."}
        )

    # 5. Unsupported / Unmeasurable stack
    return TypeSafetyResult(
        measurable=False,
        type_system="Unknown",
        unmeasurable_reason="Not measurable with the available submission."
    )
