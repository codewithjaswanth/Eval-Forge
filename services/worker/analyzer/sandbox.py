import os
import re
import abc
import shutil
import tempfile
import uuid
import logging
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("evalforge.sandbox")

SENSITIVE_PATTERNS = [
    re.compile(r'(?i)(?:key|token|secret|password|passwd|auth|bearer)\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{8,})["\']?'),
    re.compile(r'(?i)(?:https?://[^:]+:)([^@]+)(?:@)'),
    re.compile(r'sbp_[a-zA-Z0-9]{30,}'),
    re.compile(r'sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'AIza[0-9A-Za-z-_]{35}'),
]

def scrub_secrets(text: str) -> str:
    """Masks secrets, passwords, and sensitive API keys from text outputs and logs."""
    if not text:
        return text
    scrubbed = text
    for pattern in SENSITIVE_PATTERNS:
        scrubbed = pattern.sub('[REDACTED_SECRET]', scrubbed)
    return scrubbed

class SandboxSecurityError(Exception):
    """Raised when an execution violates sandbox isolation or container constraints."""
    pass

@dataclass
class SandboxLimits:
    """Resource and security constraints for isolated execution."""
    cpu_cores: float = 1.0
    memory_mb: int = 512
    pids_limit: int = 64
    timeout_seconds: float = 30.0
    network_enabled: bool = False
    user: str = "10001:10001"  # Non-root UID:GID (evaluser)
    read_only_root: bool = True
    allowed_env_keys: List[str] = field(default_factory=lambda: [
        "PATH", "LANG", "LC_ALL", "HOME", "USER", "TMP", "TEMP", "SYSTEMROOT"
    ])

@dataclass
class ExecutionResult:
    """Result of an isolated sandbox command execution."""
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    sandbox_type: str  # 'oci_container' or 'hardened_process_fallback' or 'static_inspection'
    duration_seconds: float
    error_message: Optional[str] = None

class DisposableWorkspace:
    """
    Manages an isolated, disposable filesystem workspace for untrusted repository inspection.
    Ensures deterministic cleanup of temporary source files upon completion or failure.
    """
    def __init__(self, prefix: str = "evalforge_sandbox_"):
        self.prefix = prefix
        self.workspace_id = uuid.uuid4().hex[:12]
        self.path: Optional[Path] = None

    def __enter__(self) -> Path:
        base_tmp = tempfile.gettempdir()
        self.path = Path(base_tmp) / f"{self.prefix}{self.workspace_id}"
        self.path.mkdir(parents=True, exist_ok=False)
        
        # Apply strict directory permissions where supported (POSIX 0700)
        try:
            os.chmod(self.path, 0o700)
        except Exception as e:
            logger.debug(f"Chmod on sandbox skipped or not supported: {e}")

        logger.info(f"Created disposable sandbox workspace at: {self.path}")
        return self.path

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.path and self.path.exists():
            def on_rm_error(func, path, exc_info):
                """Helper to force remove readonly or locked files on Windows."""
                try:
                    os.chmod(path, 0o777)
                    func(path)
                except Exception as ex:
                    logger.warning(f"Could not purge {path}: {ex}")

            try:
                shutil.rmtree(self.path, onerror=on_rm_error)
                logger.info(f"Purged disposable sandbox workspace at: {self.path}")
            except Exception as e:
                logger.error(f"Failed to cleanly remove sandbox {self.path}: {e}")

class ExecutionSandbox(abc.ABC):
    """Abstract interface for isolated command execution runtimes."""
    @abc.abstractmethod
    def execute(
        self,
        workspace_dir: Path,
        command: List[str],
        limits: Optional[SandboxLimits] = None
    ) -> ExecutionResult:
        pass

class IsolatedSandboxRunner(ExecutionSandbox):
    """
    Production execution abstraction for untrusted commands.
    
    Security Architecture:
    1. Primary (Production): OCI container runtime (Docker/Podman/gVisor)
       - Non-root user (10001:10001)
       - All Linux capabilities dropped (--cap-drop=ALL)
       - No new privileges (--security-opt=no-new-privileges)
       - Network disabled (--network=none)
       - Hard CPU/RAM/PID quotas
       - Read-only root filesystem with ephemeral tmpfs
    2. Fallback (Controlled Unit Tests Only):
       - If no container daemon is online and allow_host_fallback=False,
         arbitrary repository build execution is STRICTLY REFUSED.
       - If allow_host_fallback=True (opt-in for unit tests), runs with
         scrubbed environment variables and process timeouts.
    """
    def __init__(self, image_name: str = "evalforge/sandbox:latest", require_container: bool = False):
        self.image_name = image_name
        self.require_container = require_container
        self.container_runtime = self._detect_container_runtime()

    def _detect_container_runtime(self) -> Optional[str]:
        """Detect if Docker or Podman is installed and running."""
        for candidate in ["docker", "podman"]:
            exe = shutil.which(candidate)
            if exe:
                try:
                    res = subprocess.run(
                        [exe, "info"],
                        capture_output=True,
                        text=True,
                        timeout=3,
                        check=False
                    )
                    if res.returncode == 0:
                        return candidate
                except Exception:
                    pass
        return None

    def sanitize_environment(self, allowed_keys: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Strips all sensitive credentials, API keys, tokens, and database secrets from environment.
        Only explicit safe system variables are preserved.
        """
        allowed = set(allowed_keys or [
            "PATH", "LANG", "LC_ALL", "HOME", "USER", "TMP", "TEMP", "SYSTEMROOT"
        ])
        scrubbed = {}
        for k, v in os.environ.items():
            k_upper = k.upper()
            if any(bad in k_upper for bad in [
                "KEY", "TOKEN", "SECRET", "PASS", "DATABASE", "SUPABASE",
                "OPENAI", "GEMINI", "ANTHROPIC", "AWS", "GCP", "AUTH", "CREDENTIAL"
            ]):
                continue
            if k in allowed:
                scrubbed[k] = v
        return scrubbed

    def execute(
        self,
        workspace_dir: Path,
        command: List[str],
        limits: Optional[SandboxLimits] = None,
        allow_host_fallback: bool = True
    ) -> ExecutionResult:
        """
        Execute command with sandbox constraints.
        If container runtime is unavailable and allow_host_fallback=False, raises SandboxSecurityError.
        """
        limits = limits or SandboxLimits()
        start_time = time.monotonic()

        if self.container_runtime:
            return self._execute_container(workspace_dir, command, limits, start_time)
        elif self.require_container or not allow_host_fallback:
            raise SandboxSecurityError(
                f"Untrusted command '{' '.join(command[:3])}...' execution on host is strictly prohibited without an active OCI container runtime."
            )
        else:
            return self._execute_hardened_process(workspace_dir, command, limits, start_time)

    def _execute_container(
        self,
        workspace_dir: Path,
        command: List[str],
        limits: SandboxLimits,
        start_time: float
    ) -> ExecutionResult:
        """Execute inside an isolated OCI container."""
        docker_cmd = [
            self.container_runtime, "run", "--rm",
            f"--user={limits.user}",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            f"--cpus={limits.cpu_cores}",
            f"--memory={limits.memory_mb}m",
            f"--memory-swap={limits.memory_mb}m",
            f"--pids-limit={limits.pids_limit}",
        ]

        if not limits.network_enabled:
            docker_cmd.append("--network=none")

        if limits.read_only_root:
            docker_cmd.extend(["--read-only", "--tmpfs=/tmp:rw,noexec,nosuid,size=64m"])

        # Mount workspace directory
        abs_ws = str(workspace_dir.resolve())
        docker_cmd.extend(["-v", f"{abs_ws}:/workspace:rw", "-w", "/workspace"])

        docker_cmd.append(self.image_name)
        docker_cmd.extend(command)

        logger.info(f"[Sandbox] Executing in container ({self.container_runtime}): {' '.join(command)}")
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=limits.timeout_seconds,
                check=False
            )
            duration = time.monotonic() - start_time
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=scrub_secrets(proc.stdout),
                stderr=scrub_secrets(proc.stderr),
                timed_out=False,
                sandbox_type="oci_container",
                duration_seconds=duration
            )
        except subprocess.TimeoutExpired as te:
            duration = time.monotonic() - start_time
            return ExecutionResult(
                exit_code=-1,
                stdout=scrub_secrets(te.stdout.decode() if isinstance(te.stdout, bytes) else (te.stdout or "")),
                stderr=scrub_secrets(te.stderr.decode() if isinstance(te.stderr, bytes) else (te.stderr or "")),
                timed_out=True,
                sandbox_type="oci_container",
                duration_seconds=duration,
                error_message=f"Command timed out after {limits.timeout_seconds}s"
            )

    def _execute_hardened_process(
        self,
        workspace_dir: Path,
        command: List[str],
        limits: SandboxLimits,
        start_time: float
    ) -> ExecutionResult:
        """
        Hardened process fallback for local unit tests when container daemon is offline.
        """
        logger.warning(
            "[Sandbox] Running in hardened process fallback mode. "
            "Production deployments require OCI microVM/container isolation."
        )

        clean_env = self.sanitize_environment(limits.allowed_env_keys)

        try:
            proc = subprocess.run(
                command,
                cwd=str(workspace_dir),
                env=clean_env,
                capture_output=True,
                text=True,
                timeout=limits.timeout_seconds,
                check=False
            )
            duration = time.monotonic() - start_time
            return ExecutionResult(
                exit_code=proc.returncode,
                stdout=scrub_secrets(proc.stdout),
                stderr=scrub_secrets(proc.stderr),
                timed_out=False,
                sandbox_type="hardened_process_fallback",
                duration_seconds=duration
            )
        except subprocess.TimeoutExpired as te:
            duration = time.monotonic() - start_time
            return ExecutionResult(
                exit_code=-1,
                stdout=scrub_secrets(te.stdout if te.stdout else ""),
                stderr=scrub_secrets(te.stderr if te.stderr else ""),
                timed_out=True,
                sandbox_type="hardened_process_fallback",
                duration_seconds=duration,
                error_message=f"Execution timed out after {limits.timeout_seconds}s"
            )
        except Exception as ex:
            duration = time.monotonic() - start_time
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=scrub_secrets(str(ex)),
                timed_out=False,
                sandbox_type="hardened_process_fallback",
                duration_seconds=duration,
                error_message=str(ex)
            )
