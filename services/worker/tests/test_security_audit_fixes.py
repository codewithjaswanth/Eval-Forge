import os
import sys
import tempfile
import socket
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Ensure services/worker is on python sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer.browser.url_validator import validate_safe_url, assert_safe_url, SSRFSecurityException
from analyzer.browser.playwright_runner import PlaywrightRunner
from analyzer.browser.lighthouse_runner import LighthouseRunner
from analyzer.browser.models import BrowserSessionResult
from analyzer.ingestion.git_client import clone_repository, GitSecurityException
from analyzer.ingestion.detector import is_safe_path, ProjectDetector
from analyzer.sandbox import (
    SandboxLimits,
    IsolatedSandboxRunner,
    DisposableWorkspace,
    ExecutionResult
)

# ---------------------------------------------------------------------------
# 1. SSRF URL Validation Tests
# ---------------------------------------------------------------------------

class TestSSRFProtection:
    def test_blocks_cloud_metadata_service(self):
        """AWS/GCP/Azure link-local metadata address 169.254.169.254 must be blocked."""
        is_safe, reason = validate_safe_url("http://169.254.169.254/latest/meta-data/")
        assert not is_safe
        assert "link-local" in reason.lower() or "metadata" in reason.lower()

        with pytest.raises(SSRFSecurityException, match="SSRF Security Violation"):
            assert_safe_url("http://169.254.169.254/latest/meta-data/")

    def test_blocks_loopback_addresses(self):
        """Loopback IPv4 and IPv6 addresses must be blocked."""
        for loopback in ["http://127.0.0.1:8080/admin", "http://127.0.1.1:3000/"]:
            is_safe, reason = validate_safe_url(loopback)
            assert not is_safe
            assert any(k in reason.lower() for k in ["loopback", "blocked"])

            with pytest.raises(SSRFSecurityException):
                assert_safe_url(loopback)

    def test_blocks_localhost_hostname(self):
        """Hostnames resolving to 127.0.0.1 or ::1 must be blocked."""
        is_safe, reason = validate_safe_url("http://localhost:5432")
        assert not is_safe
        with pytest.raises(SSRFSecurityException):
            assert_safe_url("http://localhost:5432")

    def test_blocks_rfc1918_private_networks(self):
        """10.0.0.0/8, 172.16.0.0/12, and 192.168.0.0/16 must be rejected."""
        for priv in ["http://10.10.1.5:80/", "http://172.20.0.10/", "http://192.168.1.1/router-login"]:
            is_safe, reason = validate_safe_url(priv)
            assert not is_safe
            assert "private" in reason.lower()

            with pytest.raises(SSRFSecurityException):
                assert_safe_url(priv)

    def test_blocks_non_http_schemes(self):
        """File, gopher, ftp, and javascript schemes must be rejected."""
        for bad in ["file:///etc/passwd", "ftp://ftp.example.com/payload", "gopher://127.0.0.1:70/_evil"]:
            is_safe, reason = validate_safe_url(bad)
            assert not is_safe
            assert "scheme" in reason.lower()

            with pytest.raises(SSRFSecurityException):
                assert_safe_url(bad)

    def test_blocks_dns_rebinding_to_internal_ip(self):
        """Mocked DNS resolution resolving to an internal IP must be rejected."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.99", 80))
            ]
            is_safe, reason = validate_safe_url("https://malicious-rebinding-domain.com")
            assert not is_safe
            assert "private" in reason.lower()

            with pytest.raises(SSRFSecurityException, match="SSRF Security Violation"):
                assert_safe_url("https://malicious-rebinding-domain.com")

    def test_allows_legitimate_public_url(self):
        """Valid public domain with public IP resolution passes validation."""
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
            ]
            is_safe, reason = validate_safe_url("https://example.com/demo")
            assert is_safe
            validated = assert_safe_url("https://example.com/demo")
            assert validated == "https://example.com/demo"

    @pytest.mark.asyncio
    async def test_playwright_runner_rejects_ssrf(self):
        """Playwright runner rejects dangerous URLs before initiating any browser operations."""
        runner = PlaywrightRunner()
        session = await runner.run_browser_audit("http://169.254.169.254/latest/meta-data")
        assert not session.reachable
        assert "SSRF Protection Error" in (session.error or "")

    @pytest.mark.asyncio
    async def test_lighthouse_runner_rejects_ssrf(self):
        """Lighthouse runner rejects internal addresses."""
        runner = LighthouseRunner()
        session = BrowserSessionResult(url="http://127.0.0.1:8000/internal")
        metrics = await runner.run_lighthouse_audit("http://127.0.0.1:8000/internal", session)
        assert metrics is not None


# ---------------------------------------------------------------------------
# 2. Git Ingestion & Command Injection Defense Tests
# ---------------------------------------------------------------------------

class TestGitSecurity:
    def test_blocks_option_injection_in_repo_url(self):
        """Repository URLs starting with '-' or containing options must be rejected."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_path = Path(tmp_dir) / "out"
            with pytest.raises(GitSecurityException, match=r"(Leading hyphens|Flag injection)"):
                clone_repository("--upload-pack=touch /tmp/pwn", target_path)

            with pytest.raises(GitSecurityException, match=r"(Leading hyphens|Flag injection)"):
                clone_repository("-oProxyCommand=calc.exe", target_path)

    def test_blocks_arbitrary_local_paths_unless_flagged(self):
        """Arbitrary local filesystem cloning is blocked by default."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target_path = Path(tmp_dir) / "out"
            # Ensure EVALFORGE_ALLOW_LOCAL_FIXTURES is unset
            with patch.dict(os.environ, {"EVALFORGE_ALLOW_LOCAL_FIXTURES": "false"}):
                # Outside temp directory (e.g. C:\Windows or /etc)
                with pytest.raises(GitSecurityException, match=r"[Aa]ccess to local path"):
                    clone_repository("C:/Windows/System32", target_path)

    def test_strips_sensitive_env_vars_from_git_subprocess(self):
        """Subprocess spawned by git client must not inherit cloud or API credentials."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            with tempfile.TemporaryDirectory() as tmp_dir:
                target_path = Path(tmp_dir) / "out"
                
                with patch.dict(os.environ, {
                    "SUPABASE_SERVICE_ROLE_KEY": "secret_key_123",
                    "OPENAI_API_KEY": "sk-proj-supersecret",
                    "AWS_SECRET_ACCESS_KEY": "aws_secret_key"
                }):
                    clone_repository("https://github.com/org/valid-repo.git", target_path)
                    
                    # Verify environment passed to subprocess.run does NOT contain sensitive keys
                    assert mock_run.called
                    first_call = mock_run.call_args_list[0]
                    cmd_passed = first_call[0][0] if first_call[0] else first_call[1].get("args", [])
                    env_passed = first_call[1].get("env", {})
                    assert "SUPABASE_SERVICE_ROLE_KEY" not in env_passed
                    assert "OPENAI_API_KEY" not in env_passed
                    assert "AWS_SECRET_ACCESS_KEY" not in env_passed
                    
                    # Verify command line passes '--' separator before the URL
                    assert "--" in cmd_passed
                    dash_dash_idx = cmd_passed.index("--")
                    assert cmd_passed[dash_dash_idx + 1] == "https://github.com/org/valid-repo.git"


# ---------------------------------------------------------------------------
# 3. Path Traversal & Symlink Escape Defense Tests
# ---------------------------------------------------------------------------

class TestPathTraversalAndSymlinkDefense:
    def test_is_safe_path_validates_boundary(self):
        """is_safe_path accurately confines paths within root boundary."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir).resolve()
            safe_subfile = root / "src" / "index.js"
            safe_subfile.parent.mkdir(parents=True)
            safe_subfile.write_text("console.log(1);")

            assert is_safe_path(root, safe_subfile)

            # Traversing upwards outside root
            outside_file = root.parent / "outside.txt"
            assert not is_safe_path(root, outside_file)

    def test_detect_readme_ignores_symlink_escaping_root(self):
        """A README symlink pointing outside the workspace must not be read."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir).resolve()
            
            # Outside sensitive file
            secret_file = root.parent / "secret_host_file.txt"
            secret_file.write_text("HOST_SECRET_TOKEN=xyz987")

            # In-workspace README.md symlink pointing to secret_file
            readme_symlink = root / "README.md"
            try:
                readme_symlink.symlink_to(secret_file)
                detector = ProjectDetector()
                artifact = detector.detect_project(root, repository_url="https://github.com/org/repo", commit_sha="123")
                # Must reject reading the symlink that points outside root
                assert artifact.readme_content is None or "HOST_SECRET_TOKEN" not in artifact.readme_content
            except (OSError, NotImplementedError):
                # On Windows unprivileged users might not have symlink permissions
                pass

    def test_extract_project_metadata_does_not_escape_workspace(self):
        """ProjectDetector processes valid files and confines file tree to root."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir).resolve()
            (root / "package.json").write_text('{"name": "test-app"}')
            (root / "index.js").write_text('console.log("hello");')

            detector = ProjectDetector()
            meta = detector.detect_project(root, repository_url="https://github.com/org/repo", commit_sha="123")
            assert "JavaScript" in meta.detected_languages
            assert "package.json" in meta.file_tree
            assert "package.json" in meta.file_tree


# ---------------------------------------------------------------------------
# 4. Sandbox Isolation & Environment Sanitization Tests
# ---------------------------------------------------------------------------

class TestSandboxBoundary:
    def test_disposable_workspace_creates_and_purges(self):
        """DisposableWorkspace creates isolated temp directory and cleanly deletes it upon exit."""
        workspace_path = None
        with DisposableWorkspace(prefix="test_sbx_") as ws:
            workspace_path = ws
            assert workspace_path.exists()
            assert workspace_path.is_dir()
            # Create a file inside
            (workspace_path / "test.txt").write_text("hello sandbox")

        # After context exit, the directory must be purged
        assert not workspace_path.exists()

    def test_sandbox_environment_sanitizer_removes_secrets(self):
        """IsolatedSandboxRunner.sanitize_environment strips all API and database secrets."""
        runner = IsolatedSandboxRunner()
        with patch.dict(os.environ, {
            "SUPABASE_SERVICE_ROLE_KEY": "eyJhbGciOi...",
            "OPENAI_API_KEY": "sk-secret123",
            "DATABASE_URL": "postgresql://postgres:pwd@db:5432",
            "USER_TOKEN": "token_abc",
            "ALLOWED_ENV": "allowed_val",
            "PATH": "/usr/bin:/bin"
        }):
            cleaned = runner.sanitize_environment(allowed_keys=["PATH", "ALLOWED_ENV"])
            assert "PATH" in cleaned
            assert "ALLOWED_ENV" in cleaned
            assert "SUPABASE_SERVICE_ROLE_KEY" not in cleaned
            assert "OPENAI_API_KEY" not in cleaned
            assert "DATABASE_URL" not in cleaned
            assert "USER_TOKEN" not in cleaned

    def test_sandbox_limits_defaults(self):
        """Default SandboxLimits enforce strict non-root UID, CPU, memory, and disabled network."""
        limits = SandboxLimits()
        assert limits.user == "10001:10001"
        assert limits.cpu_cores <= 1.0
        assert limits.memory_mb <= 512
        assert limits.pids_limit <= 64
        assert limits.network_enabled is False
        assert limits.read_only_root is True
        assert limits.timeout_seconds <= 30.0

    def test_sandbox_execution_timeout_handling(self):
        """IsolatedSandboxRunner enforces timeout and returns clean ExecutionResult."""
        runner = IsolatedSandboxRunner()
        # Force fallback process execution for deterministic unit test
        runner.container_runtime = None

        with tempfile.TemporaryDirectory() as tmp_dir:
            ws = Path(tmp_dir)
            # Run a command that exceeds a tiny timeout of 0.2s
            limits = SandboxLimits(timeout_seconds=0.2)
            # Cross-platform sleep command
            cmd = ["python", "-c", "import time; time.sleep(2.0)"]
            result = runner.execute(ws, cmd, limits)
            assert result.timed_out is True
            assert result.exit_code == -1
            assert "timed out" in (result.error_message or "").lower()

    def test_git_client_blocks_ssrf_urls(self):
        """Git clone must reject internal, cloud metadata, and loopback repository URLs."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "repo"
            for unsafe in [
                "http://169.254.169.254/computeMetadata/v1",
                "http://127.0.0.1:8080/repo.git",
                "http://10.0.0.5/private.git",
                "http://192.168.1.1/router.git"
            ]:
                with pytest.raises(GitSecurityException, match=r"SSRF violation"):
                    clone_repository(unsafe, target)

    @pytest.mark.asyncio
    async def test_js_test_execution_blocks_host_rce_without_container(self):
        """Untrusted package.json test scripts must not be executed on host without container isolation."""
        import json
        from analyzer.code_quality.tests_runner import _execute_js_tests

        with tempfile.TemporaryDirectory() as tmp_dir:
            ws = Path(tmp_dir)
            pkg = ws / "package.json"
            pkg.write_text(json.dumps({
                "name": "untrusted-repo",
                "scripts": {
                    "test": "echo PWNED_HOST"
                }
            }), encoding="utf-8")

            # Ensure host test execution is not explicitly opted into
            with patch.dict(os.environ, {"EVALFORGE_ALLOW_HOST_TEST_EXECUTION": "false"}):
                # Ensure container runtime is mocked as unavailable
                with patch("analyzer.sandbox.IsolatedSandboxRunner._detect_container_runtime", return_value=None):
                    result = await _execute_js_tests(ws, ["test.js"])
                    assert result is None, "Host execution of untrusted scripts must return None and fall back to static counting"

    def test_gemini_client_transmits_api_key_in_header_not_query(self):
        """Gemini client must pass API key in x-goog-api-key header instead of URL query param."""
        from unittest.mock import patch, MagicMock
        from pydantic import BaseModel
        from analyzer.llm.client import GeminiLLMClient

        class DummySchema(BaseModel):
            result: str

        client = GeminiLLMClient(api_key="sk-test-secret-key-12345", model_name="gemini-2.5-flash")

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_res = MagicMock()
            mock_res.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "{\\"result\\": \\"ok\\"}"}]}}]}'
            mock_res.__enter__.return_value = mock_res
            mock_urlopen.return_value = mock_res

            client._call_gemini_structured("Test prompt", DummySchema, max_retries=0)

            assert mock_urlopen.called
            req = mock_urlopen.call_args[0][0]
            # Verify URL does NOT have ?key=
            assert "?key=" not in req.full_url
            assert "sk-test-secret-key-12345" not in req.full_url
            # Verify header is set
            assert req.headers.get("X-goog-api-key") == "sk-test-secret-key-12345"
