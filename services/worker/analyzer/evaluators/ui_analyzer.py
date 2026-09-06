import logging
from typing import Dict, List, Optional
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact
from ..browser import PlaywrightRunner, BrowserSessionResult

logger = logging.getLogger("evalforge.evaluators.ui")

class UIAnalyzer(BaseEvaluator):
    """
    Empirical UI/UX evaluation engine using headless Playwright.
    Audits page loading, interactive elements, forms, responsive layouts (desktop & mobile),
    console errors, accessibility violations, and visual screenshots.
    Max Score: 10.0
    Dependencies: None
    """
    def __init__(self, playwright_runner: Optional[PlaywrightRunner] = None, timeout_seconds: float = 40.0):
        super().__init__(
            name="UIAnalyzer",
            criterion="ui_ux",
            max_score=10.0,
            dependencies=[],
            timeout_seconds=timeout_seconds
        )
        self.playwright_runner = playwright_runner or PlaywrightRunner(timeout_ms=int(timeout_seconds * 1000 / 2))

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        # Case 1: No live URL provided
        if not artifact.live_url:
            if not artifact.has_frontend:
                return EvaluationResult(
                    criterion=self.criterion,
                    score=0.0,
                    maxScore=self.max_score,
                    confidence=0.0,
                    summary="Not measurable with the available submission. (No frontend codebase or live URL provided)",
                    weaknesses=["Project does not declare a frontend interface or deployed live URL."],
                    recommendations=["Provide a deployed URL or frontend codebase for UI/UX audit."],
                    evidence=[
                        EvidenceItem(
                            source="ui_analyzer",
                            metric="frontend_availability",
                            value="absent",
                            interpretation="Not measurable with the available submission."
                        )
                    ]
                )

            # Static fallback when frontend code is present but no live URL
            score = 5.0
            strengths = ["Frontend codebase present in repository."]
            weaknesses = ["No live deployed URL provided; browser viewport reflow and accessibility could not be measured dynamically."]
            recommendations = ["Deploy application and supply a live URL to enable automated multi-device Playwright testing."]
            evidence = [
                EvidenceItem(
                    source="static_inspection",
                    metric="live_url",
                    value="unmeasured",
                    interpretation="Not measurable with the available submission. (Live URL omitted by user)"
                )
            ]

            if "Tailwind CSS" in artifact.detected_frameworks or any("tailwind" in c for c in artifact.config_files):
                score += 2.0
                strengths.append("Utility-first design token architecture detected (Tailwind CSS).")
                evidence.append(EvidenceItem(
                    source="static_inspection",
                    metric="design_system",
                    value="Tailwind CSS",
                    interpretation="Design token architecture provides consistent spacing, color, and typography scales."
                ))

            score = min(score, self.max_score)
            return EvaluationResult(
                criterion=self.criterion,
                score=score,
                maxScore=self.max_score,
                confidence=0.50,
                summary=f"UI/UX evaluated statically at {score}/{self.max_score} (Live URL omitted).",
                strengths=strengths,
                weaknesses=weaknesses,
                recommendations=recommendations,
                evidence=evidence
            )

        # Case 2: Live URL provided -> Execute Playwright Browser Audit
        session: BrowserSessionResult = await self.playwright_runner.run_browser_audit(artifact.live_url)

        if not session.reachable:
            return EvaluationResult(
                criterion=self.criterion,
                score=0.0,
                maxScore=self.max_score,
                confidence=0.20,
                summary=f"Live deployment evaluation failed: URL {artifact.live_url} was unreachable ({session.error}).",
                weaknesses=[f"Live URL failed to load in browser: {session.error}"],
                recommendations=["Verify live website deployment is publicly accessible and returns HTTP 200."],
                evidence=[
                    EvidenceItem(
                        source="playwright",
                        metric="url_reachable",
                        value=False,
                        interpretation=f"Connection error: {session.error}"
                    )
                ]
            )

        evidence_items: List[EvidenceItem] = []
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendations: List[str] = []

        # ----------------------------------------------------------------------
        # 1. Interactive Elements & Navigation (up to 3.0 pts)
        # ----------------------------------------------------------------------
        total_interactive = session.interactive.button_count + session.interactive.link_count + session.interactive.input_count
        if total_interactive >= 5:
            interactive_pts = 3.0
            strengths.append(f"Rich interactive interface detected ({session.interactive.button_count} buttons, {session.interactive.link_count} links).")
        elif total_interactive > 0:
            interactive_pts = 2.0
            strengths.append(f"Interactive elements detected ({total_interactive} total elements).")
        else:
            interactive_pts = 1.0
            weaknesses.append("Very few interactive elements found on landing page.")

        evidence_items.append(EvidenceItem(
            source="playwright_dom",
            metric="interactive_elements",
            value=total_interactive,
            interpretation=f"Page contains {session.interactive.button_count} buttons, {session.interactive.link_count} links, {session.interactive.input_count} inputs.",
            raw_data={
                "buttons": session.interactive.button_count,
                "links": session.interactive.link_count,
                "inputs": session.interactive.input_count,
                "sample_labels": session.interactive.sample_interactive_labels
            }
        ))

        # ----------------------------------------------------------------------
        # 2. Responsive Layouts: Desktop & Mobile Viewports (up to 2.5 pts)
        # ----------------------------------------------------------------------
        responsive_pts = 0.0
        if session.responsive.desktop_rendered:
            responsive_pts += 1.0
        if session.responsive.mobile_rendered:
            responsive_pts += 1.0

        if session.responsive.mobile_rendered:
            if not session.responsive.mobile_horizontal_overflow:
                responsive_pts += 0.5
                strengths.append("Mobile viewport (375x667) renders cleanly with no horizontal scroll overflow.")
            else:
                weaknesses.append("Mobile layout has horizontal overflow (content exceeds 375px viewport width).")
                recommendations.append("Fix CSS overflow on mobile devices using responsive max-w and overflow-x-hidden.")

        evidence_items.append(EvidenceItem(
            source="playwright_viewport",
            metric="responsive_layout",
            value="valid" if not session.responsive.mobile_horizontal_overflow else "overflow_detected",
            interpretation=f"Desktop rendered: {session.responsive.desktop_rendered}. Mobile rendered: {session.responsive.mobile_rendered}. Mobile overflow: {session.responsive.mobile_horizontal_overflow}.",
            raw_data={
                "desktop_scroll_width": session.responsive.desktop_scroll_width,
                "mobile_scroll_width": session.responsive.mobile_scroll_width,
                "mobile_overflow": session.responsive.mobile_horizontal_overflow
            }
        ))

        # ----------------------------------------------------------------------
        # 3. Form Detection & Structure (up to 1.5 pts)
        # ----------------------------------------------------------------------
        if session.interactive.form_count > 0:
            forms_with_submits = sum(1 for f in session.interactive.forms if f.has_submit_button)
            forms_with_labels = sum(1 for f in session.interactive.forms if all(field.has_label for field in f.fields))

            if forms_with_submits > 0:
                form_pts = 1.5
                strengths.append(f"Detectable form(s) verified with valid submit controls ({session.interactive.form_count} form(s)).")
            else:
                form_pts = 1.0
                weaknesses.append("Form detected without an explicit submit button.")

            evidence_items.append(EvidenceItem(
                source="playwright_forms",
                metric="forms_detected",
                value=session.interactive.form_count,
                interpretation=f"Found {session.interactive.form_count} form(s) with {forms_with_submits} submit button(s).",
                raw_data={"forms": [f.__dict__ for f in session.interactive.forms]}
            ))
        else:
            form_pts = 1.5  # No forms required for content/dashboard page
            evidence_items.append(EvidenceItem(
                source="playwright_forms",
                metric="forms_detected",
                value=0,
                interpretation="No forms detected on initial landing page."
            ))

        # ----------------------------------------------------------------------
        # 4. Accessibility (a11y) Evaluation (up to 2.0 pts)
        # ----------------------------------------------------------------------
        a11y_violations = session.accessibility.violations_count
        a11y_pts = max(0.0, 2.0 - (a11y_violations * 0.4))

        if a11y_violations == 0:
            strengths.append("Zero WCAG accessibility violations flagged (images have alt, inputs have labels, title present).")
        else:
            for v in session.accessibility.violations_summary:
                weaknesses.append(f"Accessibility issue: {v}")
            recommendations.append("Remediate WCAG violations: add missing alt attributes, input labels, and document title.")

        evidence_items.append(EvidenceItem(
            source="accessibility_audit",
            metric="accessibility_violations",
            value=a11y_violations,
            interpretation=f"Accessibility audit detected {a11y_violations} potential violation(s).",
            raw_data={
                "violations": session.accessibility.violations_summary,
                "images_with_alt": session.accessibility.images_with_alt,
                "total_images": session.accessibility.total_images,
                "has_title": session.accessibility.has_title,
                "has_lang": session.accessibility.has_lang,
                "headings": session.accessibility.heading_counts
            }
        ))

        # ----------------------------------------------------------------------
        # 5. Console & Visual Health (up to 1.0 pt)
        # ----------------------------------------------------------------------
        console_errors = [m for m in session.console_messages if m.type == "error"]
        failed_reqs = session.failed_requests

        health_pts = max(0.0, 1.0 - (len(console_errors) * 0.3) - (len(failed_reqs) * 0.2))
        if console_errors:
            weaknesses.append(f"Encountered {len(console_errors)} JavaScript console error(s) during page load.")
            recommendations.append("Inspect browser developer console and resolve runtime JavaScript exceptions.")
        else:
            strengths.append("Zero unhandled JavaScript console errors on initial load.")

        evidence_items.append(EvidenceItem(
            source="browser_console",
            metric="console_errors",
            value=len(console_errors),
            interpretation=f"Page produced {len(console_errors)} console error(s) and {len(failed_reqs)} failed request(s).",
            raw_data={
                "console_errors": [m.text for m in console_errors[:5]],
                "failed_requests": [f.url for f in failed_reqs[:5]]
            }
        ))

        # ----------------------------------------------------------------------
        # Attach Screenshots
        # ----------------------------------------------------------------------
        if session.desktop_screenshot_base64:
            evidence_items.append(EvidenceItem(
                source="playwright_screenshot",
                metric="desktop_viewport_screenshot",
                value="captured",
                interpretation="Captured 1280x800 desktop viewport screenshot.",
                raw_data={"screenshot_base64_sample": session.desktop_screenshot_base64[:100] + "..."}
            ))

        total_score = round(min(self.max_score, max(0.0, interactive_pts + responsive_pts + form_pts + a11y_pts + health_pts)), 2)
        confidence = 0.95

        summary = (
            f"Empirical UI/UX scored {total_score:.1f}/{self.max_score} via Playwright "
            f"(Interactive: {interactive_pts:.1f}/3.0, Responsive: {responsive_pts:.1f}/2.5, "
            f"Forms: {form_pts:.1f}/1.5, Accessibility: {a11y_pts:.1f}/2.0, Health: {health_pts:.1f}/1.0)."
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
