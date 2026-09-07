import os
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from ..models import ProjectArtifact
from ..project_context import ProjectContext

logger = logging.getLogger("evalforge.detector")

def is_safe_path(root_path: Path, target_path: Path) -> bool:
    """Verifies that target_path resolves strictly within root_path, preventing symlink traversal attacks."""
    try:
        root_resolved = root_path.resolve()
        target_resolved = target_path.resolve()
        return target_resolved == root_resolved or root_resolved in target_resolved.parents
    except Exception:
        return False

class ProjectDetector:
    """
    Deterministically detects languages, frameworks, package managers, build systems,
    architecture flags (frontend/backend), tests, CI/CD, and configurations from the repository workspace.
    Includes strict symlink and path traversal guards against malicious repos.
    """

    LANGUAGE_EXTENSIONS = {
        "TypeScript": [".ts", ".tsx"],
        "JavaScript": [".js", ".jsx", ".mjs", ".cjs"],
        "Python": [".py"],
        "Go": [".go"],
        "Rust": [".rs"],
        "Java": [".java"],
        "C++": [".cpp", ".cc", ".cxx", ".hpp", ".h"],
        "C": [".c", ".h"],
        "C#": [".cs"],
        "Ruby": [".rb"],
        "PHP": [".php"],
        "Swift": [".swift"],
        "Kotlin": [".kt", ".kts"],
        "HTML": [".html", ".htm"],
        "CSS": [".css", ".scss", ".sass", ".less"],
        "SQL": [".sql"]
    }

    IGNORE_DIRS = {
        ".git", "node_modules", ".next", "dist", "build", "out",
        "venv", ".venv", "env", "__pycache__", ".pytest_cache",
        "target", "vendor", "bin", "obj", "coverage", ".nyc_output",
        ".turbo", ".cache", "tmp", "temp", ".idea", ".vscode",
        ".tox", ".yarn", ".pnpm-store"
    }

    MAX_FILES_SCANNED = 5000

    def detect_project(
        self,
        root_path: Path,
        repository_url: str,
        commit_sha: str,
        branch: str = "main",
        live_url: str = None,
        description: str = None
    ) -> ProjectArtifact:
        """Analyze cloned repository root and return normalized ProjectArtifact."""
        file_tree = []
        ext_counts: Dict[str, int] = {}
        is_truncated = False
        
        test_directories = []
        test_files = []
        ci_cd_workflows = []
        docker_files = []
        config_files = []

        # 1. Walk filesystem with strict symlink / path traversal protection
        for root, dirs, files in os.walk(root_path):
            if len(file_tree) >= self.MAX_FILES_SCANNED:
                is_truncated = True
                logger.warning(f"[Detector] Repository exceeds maximum scan limit ({self.MAX_FILES_SCANNED} files). Truncating file tree.")
                break

            # Prune ignored directories and symlinks escaping root
            dirs[:] = [
                d for d in dirs
                if d not in self.IGNORE_DIRS and is_safe_path(root_path, Path(root) / d)
            ]
            rel_root = os.path.relpath(root, root_path)

            if rel_root != ".":
                # Check for test directories
                norm_rel = rel_root.replace("\\", "/")
                if any(t in norm_rel.lower() for t in ["test", "tests", "__tests__", "spec", "specs"]):
                    if norm_rel not in test_directories:
                        test_directories.append(norm_rel)

            for file in files:
                full_file = Path(root) / file
                # Guard against symlinks pointing outside sandbox workspace
                if not is_safe_path(root_path, full_file):
                    logger.warning(f"[Security] Skipped symlink escaping workspace root: {full_file}")
                    continue

                rel_file_path = os.path.normpath(os.path.join(rel_root, file)).replace("\\", "/")
                if rel_file_path.startswith("./"):
                    rel_file_path = rel_file_path[2:]
                file_tree.append(rel_file_path)

                # Extension frequency
                _, ext = os.path.splitext(file)
                if ext:
                    ext_counts[ext.lower()] = ext_counts.get(ext.lower(), 0) + 1

                # Detect test files
                lower_file = file.lower()
                if any(keyword in lower_file for keyword in ["test_", "_test", ".test.", ".spec.", "_spec."]):
                    test_files.append(rel_file_path)

                # Detect CI/CD workflows
                if ".github/workflows" in rel_file_path or lower_file in [".gitlab-ci.yml", "jenkinsfile", ".circleci"]:
                    ci_cd_workflows.append(rel_file_path)

                # Detect Docker files
                if lower_file.startswith("dockerfile") or lower_file.startswith("docker-compose") or lower_file == ".dockerignore":
                    docker_files.append(rel_file_path)

                # Detect Config files
                if lower_file in [
                    "package.json", "tsconfig.json", "pyproject.toml", "requirements.txt",
                    "cargo.toml", "go.mod", "tailwind.config.js", "tailwind.config.ts",
                    "vite.config.ts", "vite.config.js", "next.config.js", "next.config.ts",
                    "next.config.mjs", ".env.example", ".eslintrc.json", "eslint.config.js",
                    "pom.xml", "build.gradle"
                ]:
                    config_files.append(rel_file_path)

        # 2. Detect Languages by file presence
        detected_languages = []
        for lang, exts in self.LANGUAGE_EXTENSIONS.items():
            count = sum(ext_counts.get(ext, 0) for ext in exts)
            if count > 0:
                detected_languages.append((lang, count))
        # Sort by file count descending
        detected_languages.sort(key=lambda x: x[1], reverse=True)
        detected_languages_list = [lang for lang, _ in detected_languages]

        # 3. Detect Frameworks, Package Managers & Build Systems
        detected_frameworks = []
        package_managers = []
        build_systems = []
        has_frontend = False
        has_backend = False

        # Read package.json if present in root or discovered in config_files
        pkg_json_candidates = [root_path / f for f in config_files if f.endswith("package.json") and is_safe_path(root_path, root_path / f)]
        if (root_path / "package.json").exists() and (root_path / "package.json") not in pkg_json_candidates:
            pkg_json_candidates.append(root_path / "package.json")

        for pkg_json_path in pkg_json_candidates:
            if "npm" not in package_managers:
                package_managers.append("npm")
            pkg_dir = pkg_json_path.parent
            if (pkg_dir / "yarn.lock").exists() or (root_path / "yarn.lock").exists():
                if "yarn" not in package_managers:
                    package_managers.append("yarn")
            if (pkg_dir / "pnpm-lock.yaml").exists() or (root_path / "pnpm-lock.yaml").exists():
                if "pnpm" not in package_managers:
                    package_managers.append("pnpm")
            if (pkg_dir / "bun.lockb").exists() or (pkg_dir / "bun.lock").exists() or (root_path / "bun.lockb").exists():
                if "bun" not in package_managers:
                    package_managers.append("bun")

            try:
                with open(pkg_json_path, "r", encoding="utf-8") as f:
                    pkg_data = json.load(f)
                    deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
                    
                    if "next" in deps:
                        if "Next.js" not in detected_frameworks:
                            detected_frameworks.append("Next.js")
                        has_frontend = True
                        has_backend = True  # Next.js App Router / API routes
                    if "react" in deps:
                        if "React" not in detected_frameworks:
                            detected_frameworks.append("React")
                        has_frontend = True
                    if "vue" in deps:
                        if "Vue" not in detected_frameworks:
                            detected_frameworks.append("Vue")
                        has_frontend = True
                    if "svelte" in deps:
                        if "Svelte" not in detected_frameworks:
                            detected_frameworks.append("Svelte")
                        has_frontend = True
                    if "express" in deps or "fastify" in deps or "koa" in deps or "@nestjs/core" in deps:
                        if "Node.js Server" not in detected_frameworks:
                            detected_frameworks.append("Node.js Server")
                        has_backend = True
                    if "tailwindcss" in deps:
                        if "Tailwind CSS" not in detected_frameworks:
                            detected_frameworks.append("Tailwind CSS")
                    if "vite" in deps:
                        if "Vite" not in build_systems:
                            build_systems.append("Vite")
                    if "webpack" in deps:
                        if "Webpack" not in build_systems:
                            build_systems.append("Webpack")
                    if "turbopack" in deps:
                        if "Turbopack" not in build_systems:
                            build_systems.append("Turbopack")
            except Exception as e:
                logger.warning(f"Error parsing package.json at {pkg_json_path}: {e}")

        # Python dependencies check across root and subdirectories
        py_candidates = [
            root_path / f for f in config_files 
            if any(f.endswith(cfg) for cfg in ["requirements.txt", "pyproject.toml", "Pipfile"])
            and is_safe_path(root_path, root_path / f)
        ]
        for default_py in ["requirements.txt", "pyproject.toml", "Pipfile"]:
            p = root_path / default_py
            if p.exists() and p not in py_candidates:
                py_candidates.append(p)

        if py_candidates:
            if "pip" not in package_managers:
                package_managers.append("pip")
            req_content = ""
            for p in py_candidates:
                try:
                    req_content += p.read_text(encoding="utf-8", errors="ignore").lower() + "\n"
                except Exception:
                    pass
            if "fastapi" in req_content:
                if "FastAPI" not in detected_frameworks:
                    detected_frameworks.append("FastAPI")
                has_backend = True
            if "django" in req_content:
                if "Django" not in detected_frameworks:
                    detected_frameworks.append("Django")
                has_backend = True
            if "flask" in req_content:
                if "Flask" not in detected_frameworks:
                    detected_frameworks.append("Flask")
                has_backend = True
            if "poetry" in req_content:
                if "poetry" not in package_managers:
                    package_managers.append("poetry")

        # Go check
        if (root_path / "go.mod").exists():
            package_managers.append("go modules")
            build_systems.append("go build")
            has_backend = True

        # Rust check
        if (root_path / "Cargo.toml").exists():
            package_managers.append("cargo")
            build_systems.append("cargo")

        # Heuristic frontend / backend checks if not detected via deps
        if not has_frontend:
            if any(
                p.endswith(".html") or 
                "src/app" in p or 
                "src/pages" in p or 
                "app/page." in p or 
                "pages/index." in p or 
                p.startswith("frontend/") or
                "/frontend/" in p
                for p in file_tree
            ):
                has_frontend = True
        if not has_backend:
            if any(
                p.endswith("server.py") or 
                p.endswith("main.py") or 
                p.endswith("app.py") or 
                p.endswith("server.js") or 
                "src/api" in p or 
                "api/" in p or
                p.startswith("backend/") or
                "/backend/" in p
                for p in file_tree
            ):
                has_backend = True

        # 4. Detect README
        has_readme = False
        readme_content = None
        for cand in ["README.md", "readme.md", "README.rst", "README.txt", "README"]:
            cand_path = root_path / cand
            if cand_path.exists() and is_safe_path(root_path, cand_path):
                has_readme = True
                try:
                    readme_content = cand_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    readme_content = "Failed to read README content"
                break

        artifact = ProjectArtifact(
            root_path=root_path,
            source_type="git_clone",
            repository_url=repository_url,
            commit_sha=commit_sha,
            branch=branch,
            live_url=live_url,
            description=description,
            detected_languages=detected_languages_list,
            detected_frameworks=list(set(detected_frameworks)),
            package_managers=list(set(package_managers)),
            build_systems=list(set(build_systems)),
            has_frontend=has_frontend,
            has_backend=has_backend,
            has_readme=has_readme,
            readme_content=readme_content,
            test_directories=test_directories,
            test_files=test_files,
            ci_cd_workflows=ci_cd_workflows,
            docker_files=docker_files,
            config_files=config_files,
            file_tree=file_tree,
            metadata={
                "total_files": len(file_tree),
                "extension_summary": ext_counts,
                "is_truncated": is_truncated
            }
        )
        artifact.shared_context = ProjectContext.build_from_artifact(artifact)
        return artifact
