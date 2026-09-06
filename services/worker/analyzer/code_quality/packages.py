import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("evalforge.packages")

@dataclass
class PackageAnalysisResult:
    measurable: bool
    package_manager: Optional[str] = None
    is_valid: bool = True
    dependency_count: int = 0
    dev_dependency_count: int = 0
    has_lockfile: bool = False
    metadata_issues: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    unmeasurable_reason: Optional[str] = None

def _validate_package_json(root_path: Path) -> PackageAnalysisResult:
    pkg_path = root_path / "package.json"
    if not pkg_path.exists():
        return PackageAnalysisResult(
            measurable=False,
            unmeasurable_reason="Not measurable with the available submission."
        )

    issues = []
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8", errors="ignore"))
    except Exception as e:
        return PackageAnalysisResult(
            measurable=True,
            package_manager="npm/node",
            is_valid=False,
            metadata_issues=[f"Corrupted package.json syntax: {str(e)}"]
        )

    if not isinstance(data, dict):
        return PackageAnalysisResult(
            measurable=True,
            package_manager="npm/node",
            is_valid=False,
            metadata_issues=["package.json root must be a JSON object"]
        )

    # Required / recommended field validations
    if not data.get("name"):
        issues.append("Missing required 'name' field in package.json")
    if not data.get("version"):
        issues.append("Missing 'version' field in package.json")
    if not data.get("scripts"):
        issues.append("No 'scripts' dictionary defined in package.json")
    elif not any(s in data["scripts"] for s in ["build", "test", "dev", "start"]):
        issues.append("Missing standard lifecycle scripts (build, dev, test) in package.json")

    if not data.get("license"):
        issues.append("Missing open-source 'license' identifier in package.json")

    deps = data.get("dependencies", {})
    dev_deps = data.get("devDependencies", {})
    dep_count = len(deps) if isinstance(deps, dict) else 0
    dev_dep_count = len(dev_deps) if isinstance(dev_deps, dict) else 0

    has_lock = any((root_path / f).exists() for f in ["package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb"])
    if not has_lock:
        issues.append("Missing deterministic package lockfile (e.g. pnpm-lock.yaml, package-lock.json)")

    return PackageAnalysisResult(
        measurable=True,
        package_manager="Node / npm",
        is_valid=len(issues) == 0 or (len(issues) <= 2 and "Corrupted" not in str(issues)),
        dependency_count=dep_count,
        dev_dependency_count=dev_dep_count,
        has_lockfile=has_lock,
        metadata_issues=issues,
        details={
            "name": data.get("name"),
            "version": data.get("version"),
            "scripts_count": len(data.get("scripts", {})) if isinstance(data.get("scripts"), dict) else 0,
            "license": data.get("license")
        }
    )

def _validate_python_packages(root_path: Path) -> PackageAnalysisResult:
    pyproject = root_path / "pyproject.toml"
    reqs = root_path / "requirements.txt"
    setup = root_path / "setup.py"

    if not pyproject.exists() and not reqs.exists() and not setup.exists():
        return PackageAnalysisResult(
            measurable=False,
            unmeasurable_reason="Not measurable with the available submission."
        )

    issues = []
    dep_count = 0
    has_lock = any((root_path / f).exists() for f in ["poetry.lock", "Pipfile.lock", "uv.lock", "pdm.lock"])

    if reqs.exists():
        try:
            lines = [l.strip() for l in reqs.read_text(encoding="utf-8", errors="ignore").splitlines()]
            dep_lines = [l for l in lines if l and not l.startswith("#") and not l.startswith("-")]
            dep_count += len(dep_lines)
            unpinned = [l for l in dep_lines if "==" not in l and ">=" not in l]
            if len(unpinned) > (len(dep_lines) // 2) and len(dep_lines) > 2:
                issues.append("Dependencies in requirements.txt lack pinned versions (==).")
        except Exception:
            pass

    if pyproject.exists():
        try:
            txt = pyproject.read_text(encoding="utf-8", errors="ignore")
            if "[project]" not in txt and "[tool.poetry]" not in txt and "[tool.flit]" not in txt:
                issues.append("pyproject.toml does not define a modern [project] or [tool.poetry] build specification.")
        except Exception:
            pass

    if not has_lock and not reqs.exists():
        issues.append("Missing Python lockfile or requirements.txt for reproducible builds.")

    return PackageAnalysisResult(
        measurable=True,
        package_manager="Python / pip",
        is_valid=True,
        dependency_count=dep_count,
        dev_dependency_count=0,
        has_lockfile=has_lock or reqs.exists(),
        metadata_issues=issues,
        details={"pyproject_present": pyproject.exists(), "requirements_present": reqs.exists()}
    )

def _validate_cargo_packages(root_path: Path) -> PackageAnalysisResult:
    cargo = root_path / "Cargo.toml"
    if not cargo.exists():
        return PackageAnalysisResult(measurable=False, unmeasurable_reason="Not measurable with the available submission.")
    has_lock = (root_path / "Cargo.lock").exists()
    return PackageAnalysisResult(
        measurable=True,
        package_manager="Cargo / Rust",
        is_valid=True,
        dependency_count=1,
        dev_dependency_count=0,
        has_lockfile=has_lock,
        metadata_issues=[] if has_lock else ["Cargo.lock missing from repository"],
        details={"cargo_present": True}
    )

def analyze_package_metadata(root_path: Path, package_managers: List[str]) -> PackageAnalysisResult:
    """Validate package manifest schemas, dependency counts, and lockfile presence."""
    # Check package.json first
    if (root_path / "package.json").exists():
        return _validate_package_json(root_path)

    # Check Python manifests
    if any((root_path / f).exists() for f in ["pyproject.toml", "requirements.txt", "setup.py"]):
        return _validate_python_packages(root_path)

    # Check Cargo
    if (root_path / "Cargo.toml").exists():
        return _validate_cargo_packages(root_path)

    # Unsupported or unmanifested repository
    return PackageAnalysisResult(
        measurable=False,
        unmeasurable_reason="Not measurable with the available submission."
    )
