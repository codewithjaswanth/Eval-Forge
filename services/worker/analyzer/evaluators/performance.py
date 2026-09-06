import logging
from typing import Dict, List, Optional
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact
from ..browser import PlaywrightRunner, LighthouseRunner, BrowserSessionResult, PerformanceMetrics

logger = logging.getLogger("evalforge.evaluators.performance")

class PerformanceAnalyzer(BaseEvaluator):
    """
    Empirical Performance Evaluation Engine using Playwright navigation timing,
    Core Web Vitals telemetry, and Lighthouse CLI.
    Audits TTFB, FCP, LCP, CLS, load times, network requests, and asset bundle sizes.
    Max Score: 10.0
    Dependencies: UIAnalyzer
    """
    def __init__(
        self,
        playwright_runner: Optional[PlaywrightRunner] = None,
        lighthouse_runner: Optional[LighthouseRunner] = None,
        timeout_seconds: float = 60.0
    ):
        super().__init__(
            name="PerformanceAnalyzer",
            criterion="performance",
            max_score=10.0,
            dependencies=["UIAnalyzer"],
            timeout_seconds=timeout_seconds
        )
        self.playwright_runner = playwright_runner or PlaywrightRunner(timeout_ms=15000)
        self.lighthouse_runner = lighthouse_runner or LighthouseRunner(timeout_seconds=20)

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        # Case 1: No live URL supplied -> unmeasurable
        if not artifact.live_url:
            return EvaluationResult(
                criterion=self.criterion,
                score=0.0,
                maxScore=self.max_score,
                confidence=0.0,
                summary="Not measurable with the available submission. (Requires a deployed live URL for performance and Lighthouse audits)",
                weaknesses=["Missing deployed URL to measure empirical TTFB, bundle transfer, or Core Web Vitals."],
                recommendations=["Deploy project and provide live URL to enable automated browser and Lighthouse audits."],
                evidence=[
                    EvidenceItem(
                        source="performance_audit",
                        metric="live_url_metrics",
                        value="unmeasurable",
                        interpretation="Not measurable with the available submission."
                    )
                ]
            )

        # Case 2: Live URL supplied -> Reuse or execute Playwright & Lighthouse
        shared_ctx = getattr(artifact, "shared_context", None)
        if shared_ctx and shared_ctx.browser_session is not None:
            session = shared_ctx.browser_session
        else:
            session = await self.playwright_runner.run_browser_audit(artifact.live_url)
            if shared_ctx:
                shared_ctx.browser_session = session

        if not session.reachable:
            return EvaluationResult(
                criterion=self.criterion,
                score=0.0,
                maxScore=self.max_score,
                confidence=0.20,
                summary=f"Performance evaluation failed: Target URL {artifact.live_url} was unreachable.",
                weaknesses=[f"Could not connect to live URL: {session.error}"],
                recommendations=["Verify live website is deployed and DNS / server routing is functional."],
                evidence=[
                    EvidenceItem(
                        source="playwright",
                        metric="url_reachable",
                        value=False,
                        interpretation=f"Connection failure: {session.error}"
                    )
                ]
            )

        # Run Lighthouse audit
        metrics: PerformanceMetrics = await self.lighthouse_runner.run_lighthouse_audit(artifact.live_url, session)

        evidence_items: List[EvidenceItem] = []
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendations: List[str] = []

        # ----------------------------------------------------------------------
        # 1. Load Timings & TTFB (up to 3.0 pts)
        # ----------------------------------------------------------------------
        ttfb = metrics.ttfb_ms
        load_time = metrics.load_time_ms

        ttfb_pts = 1.5 if ttfb < 600 else (1.0 if ttfb < 1200 else 0.5)
        load_pts = 1.5 if load_time < 2500 else (1.0 if load_time < 4500 else 0.5)
        timing_pts = ttfb_pts + load_pts

        if ttfb < 600:
            strengths.append(f"Fast initial server response (TTFB: {ttfb:.0f}ms).")
        else:
            weaknesses.append(f"High Time to First Byte latency (TTFB: {ttfb:.0f}ms).")
            recommendations.append("Optimize server response time, utilize edge caching, or enable CDN.")

        if load_time < 2500:
            strengths.append(f"Rapid total page load time ({load_time:.0f}ms).")
        else:
            weaknesses.append(f"Slow total page load time ({load_time:.0f}ms).")
            recommendations.append("Defer non-critical JavaScript and optimize large static assets.")

        evidence_items.append(EvidenceItem(
            source="navigation_timing",
            metric="ttfb_ms",
            value=round(ttfb, 1),
            interpretation=f"Time to First Byte measured at {ttfb:.1f}ms."
        ))
        evidence_items.append(EvidenceItem(
            source="navigation_timing",
            metric="total_load_time_ms",
            value=round(load_time, 1),
            interpretation=f"Full page load completed in {load_time:.1f}ms."
        ))

        # ----------------------------------------------------------------------
        # 2. Core Web Vitals & Layout Stability (up to 3.0 pts)
        # ----------------------------------------------------------------------
        fcp = metrics.fcp_ms
        lcp = metrics.lcp_ms
        cls_val = metrics.cls_score

        fcp_pts = 1.0 if fcp < 1800 else (0.5 if fcp < 3000 else 0.2)
        lcp_pts = 1.0 if lcp < 2500 else (0.5 if lcp < 4000 else 0.2)
        cls_pts = 1.0 if cls_val <= 0.1 else (0.5 if cls_val <= 0.25 else 0.1)
        cwv_pts = fcp_pts + lcp_pts + cls_pts

        if cls_val <= 0.1:
            strengths.append(f"Excellent layout stability (CLS: {cls_val:.3f}).")
        else:
            weaknesses.append(f"Layout shift detected (CLS: {cls_val:.3f} exceeds recommended 0.1 threshold).")
            recommendations.append("Set explicit width and height attributes on images and embed elements.")

        evidence_items.append(EvidenceItem(
            source="core_web_vitals",
            metric="core_web_vitals",
            value={"fcp_ms": round(fcp, 1), "lcp_ms": round(lcp, 1), "cls": round(cls_val, 3)},
            interpretation=f"Core Web Vitals: FCP={fcp:.0f}ms, LCP={lcp:.0f}ms, CLS={cls_val:.3f}.",
            raw_data={
                "fcp_ms": fcp,
                "lcp_ms": lcp,
                "cls_score": cls_val
            }
        ))

        # ----------------------------------------------------------------------
        # 3. Network & Asset Bundle Hygiene (up to 2.0 pts)
        # ----------------------------------------------------------------------
        failed_requests_count = len(session.failed_requests)
        js_size_mb = metrics.js_bundle_size_bytes / 1_048_576

        network_pts = max(0.0, 1.0 - (failed_requests_count * 0.5))
        bundle_pts = 1.0 if js_size_mb < 1.0 else (0.5 if js_size_mb < 3.0 else 0.2)
        efficiency_pts = network_pts + bundle_pts

        if failed_requests_count == 0:
            strengths.append(f"Zero failed HTTP requests during page load ({metrics.total_requests} requests).")
        else:
            weaknesses.append(f"Detected {failed_requests_count} failed network request(s).")
            recommendations.append("Verify all referenced image, script, and API endpoints are available.")

        evidence_items.append(EvidenceItem(
            source="network_telemetry",
            metric="network_efficiency",
            value=metrics.total_requests,
            interpretation=f"Processed {metrics.total_requests} total requests with {failed_requests_count} failures.",
            raw_data={
                "total_requests": metrics.total_requests,
                "failed_requests": failed_requests_count,
                "js_bundle_size_bytes": metrics.js_bundle_size_bytes,
                "css_bundle_size_bytes": metrics.css_bundle_size_bytes,
                "total_transfer_size_bytes": metrics.total_transfer_size_bytes
            }
        ))

        # ----------------------------------------------------------------------
        # 4. Lighthouse Performance & Best Practices (up to 2.0 pts)
        # ----------------------------------------------------------------------
        lh_score = metrics.lighthouse_performance_score if metrics.lighthouse_performance_score is not None else 80.0
        lh_pts = round(2.0 * (lh_score / 100.0), 2)

        evidence_items.append(EvidenceItem(
            source="lighthouse",
            metric="lighthouse_scores",
            value=round(lh_score, 1),
            interpretation=f"Lighthouse Performance score: {lh_score:.1f}/100.",
            raw_data={
                "performance": metrics.lighthouse_performance_score,
                "accessibility": metrics.lighthouse_accessibility_score,
                "best_practices": metrics.lighthouse_best_practices_score,
                "seo": metrics.lighthouse_seo_score
            }
        ))

        total_score = round(min(self.max_score, max(0.0, timing_pts + cwv_pts + efficiency_pts + lh_pts)), 2)
        confidence = 0.95

        summary = (
            f"Empirical performance scored {total_score:.1f}/{self.max_score} "
            f"(Load Timing: {timing_pts:.1f}/3.0, Core Web Vitals: {cwv_pts:.1f}/3.0, "
            f"Network & Assets: {efficiency_pts:.1f}/2.0, Lighthouse: {lh_pts:.1f}/2.0)."
        )

        return EvaluationResult(
            criterion=self.criterion,
            score=total_score,
            maxScore=self.max_score,
            confidence=confidence,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            evidence=evidence_items
        )
