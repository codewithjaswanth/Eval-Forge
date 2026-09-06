import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger("evalforge.context")

@dataclass
class ProjectContext:
    """
    Shared, immutable context created once during repository ingestion.
    Prevents repeated disk I/O, file tree scanning, package.json parsing,
    and duplicate browser audits across evaluators.
    """
    root_path: Path
    repository_url: str
    commit_sha: str
    branch: str = "main"
    live_url: Optional[str] = None
    description: Optional[str] = None

    # Cached manifest data parsed once
    parsed_package_json: Optional[Dict[str, Any]] = None
    dependencies: List[str] = field(default_factory=list)
    dev_dependencies: List[str] = field(default_factory=list)

    # Configuration files cache
    config_cache: Dict[str, Any] = field(default_factory=dict)

    # Pre-calculated source metrics
    source_statistics: Dict[str, Any] = field(default_factory=dict)

    # Shared browser session result (shared between UIAnalyzer & PerformanceAnalyzer)
    browser_session: Optional[Any] = None

    # Thread/Task-safe cache for AST, linters, and search queries
    cache: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build_from_artifact(cls, artifact: Any) -> "ProjectContext":
        """Factory method to construct ProjectContext from an ingested ProjectArtifact."""
        root = Path(artifact.root_path)
        ctx = cls(
            root_path=root,
            repository_url=artifact.repository_url,
            commit_sha=artifact.commit_sha,
            branch=artifact.branch,
            live_url=artifact.live_url,
            description=artifact.description,
        )

        # 1. Parse package.json once if present
        pkg_file = root / "package.json"
        if pkg_file.is_file():
            try:
                pkg_data = json.loads(pkg_file.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(pkg_data, dict):
                    ctx.parsed_package_json = pkg_data
                    ctx.dependencies = list(pkg_data.get("dependencies", {}).keys())
                    ctx.dev_dependencies = list(pkg_data.get("devDependencies", {}).keys())
            except Exception as e:
                logger.debug(f"Could not parse package.json for context: {e}")

        # 2. Cache key configuration files
        for cfg_name in [
            "tsconfig.json",
            "next.config.js",
            "next.config.ts",
            "next.config.mjs",
            "tailwind.config.js",
            "tailwind.config.ts",
            "vite.config.js",
            "vite.config.ts",
            "Dockerfile",
            "pyproject.toml",
            "requirements.txt"
        ]:
            cfg_path = root / cfg_name
            if cfg_path.is_file():
                try:
                    ctx.config_cache[cfg_name] = cfg_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    pass

        # 3. Cache source statistics
        ext_map: Dict[str, int] = {}
        for f in artifact.file_tree:
            ext = Path(f).suffix.lower()
            if ext:
                ext_map[ext] = ext_map.get(ext, 0) + 1
        ctx.source_statistics = {
            "total_files": len(artifact.file_tree),
            "extension_counts": ext_map,
            "test_files_count": len(artifact.test_files),
        }

        return ctx
