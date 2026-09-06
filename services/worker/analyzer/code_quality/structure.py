import os
import re
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Set

logger = logging.getLogger("evalforge.structure")

BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".bin", ".jar", ".class",
    ".pyc", ".pyd", ".o", ".a", ".obj", ".iso", ".dmg"
}

IGNORED_ENTRYPOINTS = {
    "index.ts", "index.tsx", "index.js", "index.jsx",
    "main.ts", "main.js", "main.py", "app.py", "server.py", "server.js",
    "page.tsx", "layout.tsx", "route.ts", "setup.py"
}

@dataclass
class StructureAnalysisResult:
    measurable: bool = True
    source_file_count: int = 0
    suspicious_issues: List[str] = field(default_factory=list)
    dead_code_candidates: List[str] = field(default_factory=list)
    todo_fixme_count: int = 0
    large_files: List[Dict[str, Any]] = field(default_factory=list)
    empty_files: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

def analyze_file_structure(root_path: Path, file_tree: List[str]) -> StructureAnalysisResult:
    """Analyze repository layout, suspicious committed artifacts, binaries, and dead code indicators."""
    suspicious_issues = []
    large_files = []
    empty_files = []
    todo_fixme_count = 0

    source_exts = {
        ".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs",
        ".java", ".c", ".cpp", ".cc", ".h", ".hpp", ".cs", ".rb", ".php"
    }

    source_files = [f for f in file_tree if any(f.endswith(ext) for ext in source_exts)]
    source_file_count = len(source_files)

    # 1. Suspicious Committed Directories Check
    for f in file_tree:
        lower = f.lower()
        if "node_modules/" in lower:
            if "Committed 'node_modules' dependency directory detected." not in suspicious_issues:
                suspicious_issues.append("Committed 'node_modules' dependency directory detected.")
        elif "venv/" in lower or ".venv/" in lower:
            if "Committed Python virtual environment directory detected." not in suspicious_issues:
                suspicious_issues.append("Committed Python virtual environment directory detected.")
        elif "__pycache__/" in lower:
            if "Committed '__pycache__' bytecode directory detected." not in suspicious_issues:
                suspicious_issues.append("Committed '__pycache__' bytecode directory detected.")

    # 2. Binary and Large File Detection
    for rel_path in file_tree:
        full_path = root_path / rel_path
        _, ext = os.path.splitext(rel_path)
        if ext.lower() in BINARY_EXTENSIONS:
            suspicious_issues.append(f"Committed executable or binary asset found: {rel_path}")

        if full_path.is_file():
            try:
                sz = full_path.stat().st_size
                if sz == 0 and any(rel_path.endswith(e) for e in source_exts):
                    empty_files.append(rel_path)
                elif sz > 1_048_576:  # > 1MB
                    large_files.append({"file": rel_path, "size_bytes": sz})
            except Exception:
                pass

    if empty_files:
        suspicious_issues.append(f"Empty source code files detected ({len(empty_files)} files: {', '.join(empty_files[:3])})")
    if large_files:
        suspicious_issues.append(f"Large files exceeding 1MB committed directly in repository ({len(large_files)} files)")

    # 3. Root Level Clutter
    root_files = [f for f in file_tree if "/" not in f and "\\" not in f]
    if len(root_files) > 25:
        suspicious_issues.append(f"Excessive root directory clutter ({len(root_files)} files directly in repository root)")

    # 4. Dead Code & Orphan File Heuristics
    # Search for source files never imported by any other source file
    dead_code_candidates = []
    if 2 < len(source_files) <= 100:
        # Build set of all text content across source files
        combined_text = ""
        for s_file in source_files:
            fp = root_path / s_file
            if fp.is_file():
                try:
                    txt = fp.read_text(encoding="utf-8", errors="ignore")
                    combined_text += " " + txt
                    # Count TODO/FIXME markers
                    todo_fixme_count += len(re.findall(r"\b(TODO|FIXME|XXX|HACK|DEPRECATED)\b", txt))
                except Exception:
                    pass

        for s_file in source_files:
            basename = os.path.basename(s_file)
            name_no_ext, _ = os.path.splitext(basename)

            if basename.lower() in IGNORED_ENTRYPOINTS or name_no_ext.startswith("test_") or ".test." in basename or ".spec." in basename:
                continue

            # Check if name or relpath is referenced anywhere in other files
            # Must appear more than once (since it appears in its own file or definition)
            # Match imports like: import ... from './basename' or from basename import ...
            occurrences = len(re.findall(r"\b" + re.escape(name_no_ext) + r"\b", combined_text))
            if occurrences <= 1:
                dead_code_candidates.append(s_file)

    return StructureAnalysisResult(
        measurable=True,
        source_file_count=source_file_count,
        suspicious_issues=suspicious_issues,
        dead_code_candidates=dead_code_candidates[:10],
        todo_fixme_count=todo_fixme_count,
        large_files=large_files,
        empty_files=empty_files,
        details={
            "source_files": source_file_count,
            "root_files_count": len(root_files),
            "total_files": len(file_tree)
        }
    )
