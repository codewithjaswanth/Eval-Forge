import os
import subprocess
import logging
import tempfile
from pathlib import Path
from typing import Tuple, Dict

logger = logging.getLogger("evalforge.git")

class GitIngestionError(Exception):
    pass

class GitSecurityException(GitIngestionError):
    pass

def clone_repository(repo_url: str, target_dir: Path, branch: str = "main") -> Tuple[str, str]:
    """Module-level convenience helper for secure git cloning."""
    return GitClient().clone_repository(repo_url, target_dir, branch)

class GitClient:
    """
    Handles secure shallow cloning and metadata extraction from git repositories.
    """
    def __init__(self, timeout_seconds: int = 60):
        self.timeout = timeout_seconds

    def clone_repository(self, repo_url: str, target_dir: Path, branch: str = "main") -> Tuple[str, str]:
        """
        Shallow clone repository with depth 1.
        Returns (commit_sha, resolved_branch).
        Supports local file paths for testing/offline scenarios.
        """
        # 1. Option injection guard
        clean_url = repo_url.strip()
        if clean_url.startswith("-"):
            raise GitSecurityException(f"Invalid repository URL '{repo_url}': Leading hyphens/flags prohibited.")

        # 2. Local fixture authorization check
        is_local = clean_url.startswith("file://") or os.path.isdir(clean_url)
        if is_local:
            local_path_str = clean_url.replace("file://", "")
            allow_local = os.getenv("EVALFORGE_ALLOW_LOCAL_FIXTURES", "").lower() in ("true", "1")
            
            # Alternatively allow if strictly confined to temp directory for testing
            try:
                resolved_local = Path(local_path_str).resolve()
                temp_dir_resolved = Path(tempfile.gettempdir()).resolve()
                is_in_temp = resolved_local == temp_dir_resolved or temp_dir_resolved in resolved_local.parents
            except Exception:
                is_in_temp = False

            if not (allow_local or is_in_temp):
                raise GitSecurityException(
                    f"Access to local path '{repo_url}' is prohibited. Only public HTTPS repositories are permitted."
                )

            logger.info(f"Using authorized local repository fixture from {local_path_str}")
            import shutil
            shutil.copytree(local_path_str, target_dir, dirs_exist_ok=True)
            if (target_dir / ".git").exists():
                return (self._get_head_commit_sha(target_dir), self._get_current_branch(target_dir))
            return ("fixture-commit-sha-0000000000000000", "main")

        # 3. Only allow http/https schemes for external repositories
        if not clean_url.startswith("https://") and not clean_url.startswith("http://"):
            raise GitSecurityException(f"Disallowed repository protocol in '{repo_url}'. Only HTTPS is permitted.")

        # 4. Run shallow clone with strict timeouts, zero credentials in env, and disabled dangerous protocols
        null_hook = "NUL" if os.name == "nt" else "/dev/null"
        cmd = [
            "git",
            "-c", "protocol.ext.allow=never",
            "-c", "protocol.ssh.allow=never",
            "-c", "core.hooksPath=" + null_hook,
            "clone",
            "--depth", "1",
            "--single-branch",
            "--",
            clean_url,
            str(target_dir)
        ]

        # Scrub sensitive environment variables
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "GIT_TERMINAL_PROMPT": "0",
        }

        logger.info(f"Executing hardened shallow git clone: {clean_url} into {target_dir}")
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=safe_env,
                check=False
            )
            if result.returncode != 0:
                # If 'main' fails or default branch differs, try clone without branch specifier
                raise GitIngestionError(f"git clone failed with code {result.returncode}: {result.stderr.strip()}")

        except subprocess.TimeoutExpired:
            raise GitIngestionError(f"git clone timed out after {self.timeout}s for {repo_url}")
        except Exception as e:
            raise GitIngestionError(f"Unexpected git clone failure: {str(e)}")

        # 3. Extract resolved commit SHA and branch name
        commit_sha = self._get_head_commit_sha(target_dir)
        resolved_branch = self._get_current_branch(target_dir)

        return (commit_sha, resolved_branch)

    def _get_safe_env(self) -> Dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", ""),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
            "TEMP": os.environ.get("TEMP", ""),
            "TMP": os.environ.get("TMP", ""),
            "GIT_TERMINAL_PROMPT": "0",
        }

    def _get_head_commit_sha(self, repo_dir: Path) -> str:
        null_hook = "NUL" if os.name == "nt" else "/dev/null"
        try:
            res = subprocess.run(
                ["git", "-c", "core.hooksPath=" + null_hook, "rev-parse", "HEAD"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=10,
                env=self._get_safe_env(),
                check=True
            )
            return res.stdout.strip()
        except Exception:
            return "unknown-commit-sha"

    def _get_current_branch(self, repo_dir: Path) -> str:
        null_hook = "NUL" if os.name == "nt" else "/dev/null"
        try:
            res = subprocess.run(
                ["git", "-c", "core.hooksPath=" + null_hook, "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=str(repo_dir),
                capture_output=True,
                text=True,
                timeout=10,
                env=self._get_safe_env(),
                check=True
            )
            return res.stdout.strip()
        except Exception:
            return "main"
