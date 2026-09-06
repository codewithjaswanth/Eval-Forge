import asyncio
import json
import logging
import shutil
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from .models import PerformanceMetrics, BrowserSessionResult
from .url_validator import validate_safe_url

logger = logging.getLogger("evalforge.lighthouse")

class LighthouseRunner:
    """
    Executes Lighthouse audits via npx lighthouse CLI, extracting Core Web Vitals,
    Performance scores, Accessibility scores, Best Practices scores, and SEO metrics.
    """
    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    async def run_lighthouse_audit(self, url: str, session: BrowserSessionResult) -> PerformanceMetrics:
        """Runs Lighthouse audit on URL, updating and returning PerformanceMetrics."""
        metrics = session.performance

        # SSRF Check
        is_safe, reason = validate_safe_url(url)
        if not is_safe:
            logger.warning(f"[LighthouseRunner] Aborting audit for unsafe URL: {url} ({reason})")
            return self._fallback_metrics(metrics, session)

        # Check if npx is available
        npx_path = shutil.which("npx") or shutil.which("npx.cmd")
        if not npx_path:
            logger.warning("[LighthouseRunner] 'npx' executable not found. Using Playwright CDP metrics.")
            metrics.lighthouse_performance_score = 85.0 if metrics.ttfb_ms < 800 else 70.0
            metrics.lighthouse_accessibility_score = max(0.0, 100.0 - (session.accessibility.violations_count * 15.0))
            metrics.lighthouse_best_practices_score = 90.0 if not session.failed_requests else 70.0
            return metrics

        with tempfile.TemporaryDirectory(prefix="evalforge_lh_") as tmpdir:
            output_json = Path(tmpdir) / "lighthouse_report.json"
            cmd = [
                npx_path,
                "--yes",
                "lighthouse",
                url,
                "--output=json",
                f"--output-path={output_json}",
                "--chrome-flags=--headless --no-sandbox --disable-dev-shm-usage --disable-gpu",
                "--max-wait-for-load=15000",
                "--preset=desktop",
                "--only-categories=performance,accessibility,best-practices,seo"
            ]

            logger.info(f"[LighthouseRunner] Executing Lighthouse CLI for {url}...")
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
                except asyncio.TimeoutError:
                    proc.kill()
                    logger.warning(f"[LighthouseRunner] Lighthouse execution timed out after {self.timeout_seconds}s. Falling back to browser metrics.")
                    return self._fallback_metrics(metrics, session)

                if output_json.exists() and output_json.stat().st_size > 0:
                    data = json.loads(output_json.read_text(encoding="utf-8", errors="ignore"))
                    cats = data.get("categories", {})
                    audits = data.get("audits", {})

                    metrics.lighthouse_performance_score = round(cats.get("performance", {}).get("score", 0.0) * 100, 1)
                    metrics.lighthouse_accessibility_score = round(cats.get("accessibility", {}).get("score", 0.0) * 100, 1)
                    metrics.lighthouse_best_practices_score = round(cats.get("best-practices", {}).get("score", 0.0) * 100, 1)
                    metrics.lighthouse_seo_score = round(cats.get("seo", {}).get("score", 0.0) * 100, 1)

                    if "first-contentful-paint" in audits:
                        metrics.fcp_ms = float(audits["first-contentful-paint"].get("numericValue", metrics.fcp_ms))
                    if "largest-contentful-paint" in audits:
                        metrics.lcp_ms = float(audits["largest-contentful-paint"].get("numericValue", metrics.lcp_ms))
                    if "cumulative-layout-shift" in audits:
                        metrics.cls_score = round(float(audits["cumulative-layout-shift"].get("numericValue", metrics.cls_score)), 3)

                    logger.info(f"[LighthouseRunner] Lighthouse report generated. Performance score: {metrics.lighthouse_performance_score}")
                    return metrics
                else:
                    logger.warning("[LighthouseRunner] Lighthouse JSON report empty or missing. Falling back.")
                    return self._fallback_metrics(metrics, session)

            except Exception as ex:
                logger.warning(f"[LighthouseRunner] Lighthouse failed: {ex}. Falling back to browser metrics.")
                return self._fallback_metrics(metrics, session)

    def _fallback_metrics(self, metrics: PerformanceMetrics, session: BrowserSessionResult) -> PerformanceMetrics:
        """Calculates grounded fallback scores from Playwright navigation and accessibility measurements."""
        perf_score = 90.0
        if metrics.ttfb_ms > 800:
            perf_score -= 15.0
        if metrics.load_time_ms > 3000:
            perf_score -= 15.0
        if session.responsive.desktop_horizontal_overflow:
            perf_score -= 20.0
        metrics.lighthouse_performance_score = max(10.0, perf_score)

        metrics.lighthouse_accessibility_score = max(
            20.0,
            100.0 - (session.accessibility.violations_count * 15.0)
        )
        metrics.lighthouse_best_practices_score = 95.0 if not session.failed_requests else 65.0
        return metrics
