from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from pathlib import Path

@dataclass
class ProjectArtifact:
    """
    Normalized in-memory and filesystem representation of an ingested software repository.
    Decouples all downstream evaluators (CodeQuality, Security, UI, Architecture) from GitHub API.
    """
    root_path: Path
    source_type: str  # "git_clone", "local_fixture", "archive"
    repository_url: str
    commit_sha: str
    branch: str = "main"
    live_url: Optional[str] = None
    description: Optional[str] = None

    # Discovered Metadata
    detected_languages: List[str] = field(default_factory=list)
    detected_frameworks: List[str] = field(default_factory=list)
    package_managers: List[str] = field(default_factory=list)
    build_systems: List[str] = field(default_factory=list)
    
    # Architecture Flags
    has_frontend: bool = False
    has_backend: bool = False
    has_readme: bool = False
    readme_content: Optional[str] = None

    # Key Artifact Paths (relative to root_path)
    test_directories: List[str] = field(default_factory=list)
    test_files: List[str] = field(default_factory=list)
    ci_cd_workflows: List[str] = field(default_factory=list)
    docker_files: List[str] = field(default_factory=list)
    config_files: List[str] = field(default_factory=list)
    file_tree: List[str] = field(default_factory=list)

    # Additional contextual metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert artifact metadata to JSON-serializable dictionary for DB storage."""
        return {
            "source_type": self.source_type,
            "repository_url": self.repository_url,
            "commit_sha": self.commit_sha,
            "branch": self.branch,
            "live_url": self.live_url,
            "description": self.description,
            "detected_languages": self.detected_languages,
            "detected_frameworks": self.detected_frameworks,
            "package_managers": self.package_managers,
            "build_systems": self.build_systems,
            "has_frontend": self.has_frontend,
            "has_backend": self.has_backend,
            "has_readme": self.has_readme,
            "readme_snippet": (self.readme_content[:500] + "...") if self.readme_content else None,
            "test_directories": self.test_directories,
            "test_files": self.test_files[:100],
            "test_files_count": len(self.test_files),
            "ci_cd_workflows": self.ci_cd_workflows,
            "docker_files": self.docker_files,
            "config_files": self.config_files,
            "total_files": len(self.file_tree),
            "metadata": self.metadata
        }
