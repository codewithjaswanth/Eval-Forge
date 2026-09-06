import unittest
import threading
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, Any

# Add services/worker to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from analyzer.models import ProjectArtifact
from analyzer.evaluators.ui_analyzer import UIAnalyzer
from analyzer.evaluators.performance import PerformanceAnalyzer
from analyzer.evaluators.base import EvaluationResult

CLEAN_PAGE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EvalForge Test Application</title>
    <style>
        body { font-family: sans-serif; margin: 0; padding: 20px; box-sizing: border-box; }
        header { display: flex; justify-content: space-between; align-items: center; }
        nav a { margin-right: 15px; text-decoration: none; color: #0066cc; }
        .hero { margin: 40px 0; max-width: 800px; }
        .card { background: #f4f4f5; padding: 20px; border-radius: 8px; margin: 20px 0; }
        form { display: flex; flex-direction: column; gap: 10px; max-width: 400px; }
        input, textarea, button { padding: 8px; font-size: 14px; }
        button { background: #0066cc; color: white; border: none; cursor: pointer; border-radius: 4px; }
    </style>
</head>
<body>
    <header>
        <div class="logo"><strong>EvalForge</strong></div>
        <nav>
            <a href="#features">Features</a>
            <a href="#pricing">Pricing</a>
            <a href="#contact">Contact</a>
        </nav>
    </header>

    <main class="hero">
        <h1>High Precision Software Evaluation</h1>
        <p>Evidence-backed evaluations without arbitrary LLM hallucinations.</p>
        <button id="cta-button" onclick="alert('clicked')">Explore Platform</button>

        <div class="card">
            <h2>Contact Our Engineering Team</h2>
            <form action="/submit" method="POST">
                <label for="name-input">Full Name</label>
                <input id="name-input" type="text" name="name" required placeholder="Jane Doe">

                <label for="email-input">Work Email</label>
                <input id="email-input" type="email" name="email" required placeholder="jane@company.com">

                <label for="notes-input">Project Notes</label>
                <textarea id="notes-input" name="notes" rows="3"></textarea>

                <button type="submit" id="submit-btn">Send Inquiry</button>
            </form>
        </div>

        <div>
            <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==" alt="Sample Diagram" width="100" height="100">
        </div>
    </main>
</body>
</html>
"""

BROKEN_PAGE_HTML = """<!DOCTYPE html>
<html>
<head>
    <!-- Missing title and missing viewport meta -->
    <script>
        console.error("Uncaught TypeError: Cannot read properties of undefined (reading 'render')");
    </script>
</head>
<body>
    <!-- Missing h1 heading -->
    <h2>Broken Page Layout</h2>
    
    <!-- Image missing alt and pointing to non-existent endpoint to trigger failed request -->
    <img src="/broken_asset_404.png">

    <!-- Form with missing input labels and missing submit button -->
    <form action="/broken">
        <input type="text" name="unlabeled_user">
        <input type="password" name="unlabeled_pass">
    </form>

    <!-- Massive element causing horizontal viewport overflow on both desktop and mobile -->
    <div style="width: 3500px; height: 100px; background: red;">
        Massive element causing overflow
    </div>
</body>
</html>
"""

class MockSiteHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(CLEAN_PAGE_HTML.encode("utf-8"))
        elif self.path == "/broken":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(BROKEN_PAGE_HTML.encode("utf-8"))
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not Found")

    def do_POST(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Suppress standard logging during tests
        return

class TestLiveWebsiteEvaluation(unittest.IsolatedAsyncioTestCase):
    server: HTTPServer
    server_thread: threading.Thread
    port: int

    @classmethod
    def setUpClass(cls):
        import os
        os.environ["EVALFORGE_ALLOW_LOCAL_TEST_SITES"] = "true"
        cls.server = HTTPServer(("127.0.0.1", 0), MockSiteHandler)
        cls.port = cls.server.server_port
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        import os
        os.environ.pop("EVALFORGE_ALLOW_LOCAL_TEST_SITES", None)
        cls.server.shutdown()
        cls.server.server_close()

    def make_artifact(self, path: str = "") -> ProjectArtifact:
        url = f"http://127.0.0.1:{self.port}{path}"
        return ProjectArtifact(
            root_path=Path("/tmp/mock_repo"),
            source_type="test_fixture",
            repository_url="https://github.com/test-org/web-app",
            commit_sha="abcdef",
            live_url=url,
            has_frontend=True,
            detected_languages=["TypeScript", "HTML"],
            file_tree=["index.html", "src/app.ts"]
        )

    # --------------------------------------------------------------------------
    # 1. Clean Responsive Website UI Evaluation
    # --------------------------------------------------------------------------
    async def test_clean_live_website_ui_analyzer(self):
        artifact = self.make_artifact("/")
        analyzer = UIAnalyzer()

        result = await analyzer.run_safe(artifact=artifact, context={})

        self.assertTrue(analyzer.validate(result))
        self.assertEqual(result.criterion, "ui_ux")
        self.assertEqual(result.maxScore, 10.0)
        self.assertGreaterEqual(result.score, 8.5)
        self.assertEqual(result.confidence, 0.95)

        evidence = {e.metric: e for e in result.evidence}
        self.assertIn("interactive_elements", evidence)
        self.assertGreaterEqual(evidence["interactive_elements"].value, 5)

        self.assertIn("responsive_layout", evidence)
        self.assertEqual(evidence["responsive_layout"].value, "valid")
        self.assertFalse(evidence["responsive_layout"].raw_data["mobile_overflow"])

        self.assertIn("forms_detected", evidence)
        self.assertEqual(evidence["forms_detected"].value, 1)

        self.assertIn("accessibility_violations", evidence)
        self.assertEqual(evidence["accessibility_violations"].value, 0)

        self.assertIn("console_errors", evidence)
        self.assertEqual(evidence["console_errors"].value, 0)

        self.assertIn("desktop_viewport_screenshot", evidence)

    # --------------------------------------------------------------------------
    # 2. Clean Live Website Performance Evaluation
    # --------------------------------------------------------------------------
    async def test_clean_live_website_performance_analyzer(self):
        artifact = self.make_artifact("/")
        analyzer = PerformanceAnalyzer()

        result = await analyzer.run_safe(artifact=artifact, context={})

        self.assertTrue(analyzer.validate(result))
        self.assertEqual(result.criterion, "performance")
        self.assertEqual(result.maxScore, 10.0)
        self.assertGreaterEqual(result.score, 8.0)
        self.assertEqual(result.confidence, 0.95)

        evidence = {e.metric: e for e in result.evidence}
        self.assertIn("ttfb_ms", evidence)
        self.assertGreaterEqual(evidence["ttfb_ms"].value, 0.0)

        self.assertIn("total_load_time_ms", evidence)
        self.assertIn("core_web_vitals", evidence)
        self.assertIn("network_efficiency", evidence)
        self.assertEqual(evidence["network_efficiency"].raw_data["failed_requests"], 0)

    # --------------------------------------------------------------------------
    # 3. Broken Website with Console Errors & Overflow
    # --------------------------------------------------------------------------
    async def test_broken_page_penalties(self):
        artifact = self.make_artifact("/broken")
        ui_analyzer = UIAnalyzer()
        perf_analyzer = PerformanceAnalyzer()

        ui_res = await ui_analyzer.run_safe(artifact=artifact, context={})
        perf_res = await perf_analyzer.run_safe(artifact=artifact, context={})

        # UIAnalyzer flags
        self.assertTrue(ui_analyzer.validate(ui_res))
        self.assertLess(ui_res.score, 7.0)  # Penalized

        ui_evidence = {e.metric: e for e in ui_res.evidence}
        self.assertGreater(ui_evidence["console_errors"].value, 0)
        self.assertEqual(ui_evidence["responsive_layout"].value, "overflow_detected")
        self.assertTrue(ui_evidence["responsive_layout"].raw_data["mobile_overflow"])
        self.assertGreater(ui_evidence["accessibility_violations"].value, 0)

        # PerformanceAnalyzer flags failed requests
        self.assertTrue(perf_analyzer.validate(perf_res))
        perf_evidence = {e.metric: e for e in perf_res.evidence}
        self.assertGreater(perf_evidence["network_efficiency"].raw_data["failed_requests"], 0)

    # --------------------------------------------------------------------------
    # 4. No Live URL Submission
    # --------------------------------------------------------------------------
    async def test_no_live_url_produces_unmeasurable(self):
        no_live_artifact = ProjectArtifact(
            root_path=Path("/tmp/mock_repo"),
            source_type="test_fixture",
            repository_url="https://github.com/test-org/no-live",
            commit_sha="999888",
            live_url=None,
            has_frontend=False
        )

        ui_analyzer = UIAnalyzer()
        perf_analyzer = PerformanceAnalyzer()

        ui_res = await ui_analyzer.run_safe(artifact=no_live_artifact, context={})
        perf_res = await perf_analyzer.run_safe(artifact=no_live_artifact, context={})

        self.assertEqual(ui_res.score, 0.0)
        self.assertEqual(ui_res.confidence, 0.0)
        self.assertIn("Not measurable with the available submission.", ui_res.summary)

        self.assertEqual(perf_res.score, 0.0)
        self.assertEqual(perf_res.confidence, 0.0)
        self.assertIn("Not measurable with the available submission.", perf_res.summary)

    # --------------------------------------------------------------------------
    # 5. Unreachable Live URL Handling
    # --------------------------------------------------------------------------
    async def test_unreachable_live_url_handling(self):
        unreachable_artifact = ProjectArtifact(
            root_path=Path("/tmp/mock_repo"),
            source_type="test_fixture",
            repository_url="https://github.com/test-org/dead-link",
            commit_sha="000111",
            live_url="http://127.0.0.1:59999/dead_endpoint",
            has_frontend=True
        )

        ui_analyzer = UIAnalyzer()
        perf_analyzer = PerformanceAnalyzer()

        ui_res = await ui_analyzer.run_safe(artifact=unreachable_artifact, context={})
        perf_res = await perf_analyzer.run_safe(artifact=unreachable_artifact, context={})

        self.assertEqual(ui_res.score, 0.0)
        self.assertIn("unreachable", ui_res.summary.lower())

        self.assertEqual(perf_res.score, 0.0)
        self.assertIn("unreachable", perf_res.summary.lower())

if __name__ == "__main__":
    unittest.main()
