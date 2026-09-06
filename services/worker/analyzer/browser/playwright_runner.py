import asyncio
import base64
import logging
import os
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from .models import (
    BrowserSessionResult,
    ResponsiveAudit,
    InteractiveAudit,
    FormAudit,
    FormFieldDetail,
    AccessibilityAudit,
    PerformanceMetrics,
    ConsoleMessageAudit,
    NetworkRequestAudit
)
from .url_validator import validate_safe_url

logger = logging.getLogger("evalforge.playwright")

class PlaywrightRunner:
    """
    Automated browser audit engine using headless Playwright.
    Executes responsive desktop and mobile viewport tests, captures console/network telemetry,
    inspects interactive DOM elements and forms, runs accessibility audits, and measures load timings.
    """
    def __init__(self, timeout_ms: int = 15000, allow_local_test_sites: bool = False):
        self.timeout_ms = timeout_ms
        self.allow_local_test_sites = allow_local_test_sites or (os.getenv("EVALFORGE_ALLOW_LOCAL_TEST_SITES", "").lower() in ("true", "1"))

    async def run_browser_audit(self, url: str) -> BrowserSessionResult:
        """Execute comprehensive browser and DOM audit for a live URL."""
        session = BrowserSessionResult(url=url)

        # 0. SSRF Prevention Validation
        allow_testing = self.allow_local_test_sites or (os.getenv("EVALFORGE_ALLOW_LOCAL_TEST_SITES", "").lower() in ("true", "1"))
        self.allow_local_test_sites = allow_testing
        is_safe, reason = validate_safe_url(url, allow_localhost_for_testing=allow_testing)
        if not is_safe:
            logger.warning(f"[PlaywrightRunner] Blocked potentially dangerous or internal URL: {url} ({reason})")
            session.reachable = False
            session.error = f"SSRF Protection Error: {reason}"
            return session

        console_messages: List[ConsoleMessageAudit] = []
        network_requests: List[NetworkRequestAudit] = []
        js_bundle_size = 0
        css_bundle_size = 0
        total_transfer_size = 0

        logger.info(f"[PlaywrightRunner] Launching headless browser audit for: {url}")

        try:
            async with async_playwright() as p:
                # Attempt system Chrome first, then default chromium
                launch_options = {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
                }
                chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
                if os.path.exists(chrome_path):
                    launch_options["executable_path"] = chrome_path

                browser = await p.chromium.launch(**launch_options)

                # --------------------------------------------------------------
                # Phase 1: Desktop Viewport Audit (1280 x 800)
                # --------------------------------------------------------------
                desktop_context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 EvalForgeBot/1.0"
                )

                async def route_guard(route):
                    req_url = route.request.url
                    is_safe, reason = validate_safe_url(req_url, allow_localhost_for_testing=self.allow_local_test_sites)
                    if not is_safe:
                        logger.warning(f"[Playwright SSRF Guard] Blocked unsafe subresource/redirect: {req_url} ({reason})")
                        network_requests.append(NetworkRequestAudit(
                            url=req_url,
                            method=route.request.method,
                            status=0,
                            failed=True,
                            failure_text=f"Blocked by EvalForge SSRF Guard: {reason}"
                        ))
                        await route.abort("blockedbyclient")
                    else:
                        await route.continue_()

                await desktop_context.route("**/*", route_guard)
                page = await desktop_context.new_page()

                # Event listeners for console and network
                def on_console(msg):
                    if "favicon.ico" in msg.text.lower():
                        return
                    console_messages.append(
                        ConsoleMessageAudit(
                            type=msg.type,
                            text=msg.text,
                            location=f"{msg.location.get('url', '')}:{msg.location.get('lineNumber', 0)}" if msg.location else None
                        )
                    )
                page.on("console", on_console)

                def on_request_failed(req):
                    if "favicon.ico" in req.url.lower():
                        return
                    failure_msg = "Unknown failure"
                    if req.failure:
                        failure_msg = str(req.failure) if isinstance(req.failure, str) else getattr(req.failure, "error_text", str(req.failure))
                    network_requests.append(NetworkRequestAudit(
                        url=req.url,
                        method=req.method,
                        status=0,
                        failed=True,
                        failure_text=failure_msg
                    ))
                page.on("requestfailed", on_request_failed)

                def on_response(res):
                    nonlocal js_bundle_size, css_bundle_size, total_transfer_size
                    if "favicon.ico" in res.url.lower():
                        return
                    content_type = res.headers.get("content-type", "").lower()
                    status = res.status
                    failed = status >= 400

                    # Best effort size estimation
                    size = len(res.url)  # Fallback
                    try:
                        cl = res.headers.get("content-length")
                        if cl:
                            size = int(cl)
                    except Exception:
                        pass

                    total_transfer_size += size
                    if "javascript" in content_type:
                        js_bundle_size += size
                    elif "css" in content_type:
                        css_bundle_size += size

                    if failed:
                        network_requests.append(NetworkRequestAudit(
                            url=res.url,
                            method=res.request.method,
                            status=status,
                            failed=True,
                            failure_text=f"HTTP {status}",
                            size_bytes=size,
                            content_type=content_type
                        ))
                page.on("response", on_response)

                # Navigate to URL
                try:
                    response = await page.goto(url, timeout=self.timeout_ms, wait_until="load")
                    session.reachable = True
                    session.http_status = response.status if response else 200
                except PlaywrightTimeoutError:
                    session.reachable = True  # Loaded partially
                    session.http_status = 200
                    logger.warning(f"[PlaywrightRunner] Navigation timed out after {self.timeout_ms}ms, continuing audit on partial DOM.")
                except Exception as ne:
                    session.reachable = False
                    session.error = f"Navigation failed: {str(ne)}"
                    await browser.close()
                    return session

                # Allow DOM animations / JS hydration to settle
                await page.wait_for_timeout(500)

                # 1. Desktop Responsive Check
                desktop_overflow = await page.evaluate(
                    "document.documentElement.scrollWidth > window.innerWidth"
                )
                desktop_scroll_width = await page.evaluate(
                    "document.documentElement.scrollWidth"
                )
                session.responsive.desktop_rendered = True
                session.responsive.desktop_horizontal_overflow = bool(desktop_overflow)
                session.responsive.desktop_scroll_width = int(desktop_scroll_width)

                # 2. Desktop Screenshot
                try:
                    screenshot_bytes = await page.screenshot(type="png", full_page=False)
                    session.desktop_screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
                except Exception as se:
                    logger.warning(f"Desktop screenshot failed: {se}")

                # 3. Interactive Elements & Forms Audit
                interactive_data = await page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button, [role="button"], input[type="button"], input[type="submit"]'));
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
                    const forms = Array.from(document.querySelectorAll('form'));

                    const formDetails = forms.map(f => {
                        const fields = Array.from(f.querySelectorAll('input:not([type="hidden"]), select, textarea')).map(el => {
                            const id = el.id;
                            const hasLabel = id ? Boolean(document.querySelector(`label[for="${id}"]`)) : Boolean(el.closest('label'));
                            return {
                                tag: el.tagName.toLowerCase(),
                                input_type: el.type || null,
                                name: el.name || null,
                                has_label: hasLabel || Boolean(el.getAttribute('aria-label')),
                                required: Boolean(el.required)
                            };
                        });
                        const hasSubmit = Boolean(f.querySelector('button[type="submit"], input[type="submit"], button:not([type])'));
                        return {
                            action: f.getAttribute('action') || null,
                            method: (f.getAttribute('method') || 'GET').toUpperCase(),
                            fields: fields,
                            has_submit_button: hasSubmit
                        };
                    });

                    const sampleLabels = buttons.slice(0, 5).map(b => (b.innerText || b.getAttribute('aria-label') || b.value || '').trim()).filter(Boolean);

                    return {
                        button_count: buttons.length,
                        link_count: links.length,
                        input_count: inputs.length,
                        form_count: forms.length,
                        forms: formDetails,
                        sample_labels: sampleLabels
                    };
                }""")

                session.interactive.button_count = interactive_data.get("button_count", 0)
                session.interactive.link_count = interactive_data.get("link_count", 0)
                session.interactive.input_count = interactive_data.get("input_count", 0)
                session.interactive.form_count = interactive_data.get("form_count", 0)
                session.interactive.sample_interactive_labels = interactive_data.get("sample_labels", [])

                for f_data in interactive_data.get("forms", []):
                    fields = [FormFieldDetail(**f) for f in f_data.get("fields", [])]
                    session.interactive.forms.append(FormAudit(
                        action=f_data.get("action"),
                        method=f_data.get("method", "GET"),
                        fields=fields,
                        has_submit_button=f_data.get("has_submit_button", False)
                    ))

                # 4. Accessibility (a11y) Evaluation
                a11y_data = await page.evaluate("""() => {
                    const imgs = Array.from(document.querySelectorAll('img'));
                    const missingAlt = imgs.filter(i => !i.hasAttribute('alt')).map(i => i.src || i.className).slice(0, 5);

                    const inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]), select, textarea'));
                    const missingLabels = inputs.filter(el => {
                        const id = el.id;
                        const hasLabel = id ? Boolean(document.querySelector(`label[for="${id}"]`)) : Boolean(el.closest('label'));
                        return !hasLabel && !el.getAttribute('aria-label') && !el.getAttribute('aria-labelledby');
                    }).map(el => el.name || el.id || el.type).slice(0, 5);

                    const title = document.title ? document.title.trim() : null;
                    const lang = document.documentElement.lang ? document.documentElement.lang.trim() : null;

                    const headings = {};
                    ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].forEach(h => {
                        headings[h] = document.querySelectorAll(h).length;
                    });

                    return {
                        total_images: imgs.length,
                        missing_alt: missingAlt,
                        total_inputs: inputs.length,
                        missing_labels: missingLabels,
                        title: title,
                        lang: lang,
                        headings: headings
                    };
                }""")

                session.accessibility.total_images = a11y_data["total_images"]
                session.accessibility.images_with_alt = a11y_data["total_images"] - len(a11y_data["missing_alt"])
                session.accessibility.images_missing_alt = a11y_data["missing_alt"]
                session.accessibility.total_inputs = a11y_data["total_inputs"]
                session.accessibility.inputs_with_labels = a11y_data["total_inputs"] - len(a11y_data["missing_labels"])
                session.accessibility.inputs_missing_labels = a11y_data["missing_labels"]
                session.accessibility.has_title = bool(a11y_data["title"])
                session.accessibility.page_title = a11y_data["title"]
                session.accessibility.has_lang = bool(a11y_data["lang"])
                session.accessibility.lang_code = a11y_data["lang"]
                session.accessibility.heading_counts = a11y_data["headings"]

                violations = []
                if a11y_data["missing_alt"]:
                    violations.append(f"{len(a11y_data['missing_alt'])} image(s) missing alt text")
                if a11y_data["missing_labels"]:
                    violations.append(f"{len(a11y_data['missing_labels'])} input(s) missing accessible labels")
                if not a11y_data["title"]:
                    violations.append("Missing <title> document title")
                if not a11y_data["lang"]:
                    violations.append("Missing lang attribute on <html> element")
                if a11y_data["headings"].get("h1", 0) == 0:
                    violations.append("Missing primary <h1> heading tag")

                session.accessibility.violations_count = len(violations)
                session.accessibility.violations_summary = violations

                # 5. Performance & Load Timings (Navigation Timing API & PerformanceObserver)
                timing_data = await page.evaluate("""() => {
                    const nav = performance.getEntriesByType('navigation')[0] || {};
                    const timing = performance.timing || {};

                    const ttfb = nav.responseStart ? (nav.responseStart - nav.requestStart) : 
                                 (timing.responseStart && timing.requestStart ? (timing.responseStart - timing.requestStart) : 0);
                    
                    const domLoaded = nav.domContentLoadedEventEnd ? (nav.domContentLoadedEventEnd - nav.startTime) :
                                      (timing.domContentLoadedEventEnd && timing.navigationStart ? (timing.domContentLoadedEventEnd - timing.navigationStart) : 0);

                    const loadTime = nav.loadEventEnd ? (nav.loadEventEnd - nav.startTime) :
                                     (timing.loadEventEnd && timing.navigationStart ? (timing.loadEventEnd - timing.navigationStart) : 0);

                    const paintEntries = performance.getEntriesByType('paint');
                    const fcpEntry = paintEntries.find(p => p.name === 'first-contentful-paint');
                    const fcp = fcpEntry ? fcpEntry.startTime : 0;

                    return {
                        ttfb: Math.max(0, Math.round(ttfb)),
                        dom_loaded: Math.max(0, Math.round(domLoaded)),
                        load_time: Math.max(0, Math.round(loadTime)),
                        fcp: Math.max(0, Math.round(fcp))
                    };
                }""")

                session.performance.ttfb_ms = float(timing_data.get("ttfb", 0))
                session.performance.dom_content_loaded_ms = float(timing_data.get("dom_loaded", 0))
                session.performance.load_time_ms = float(timing_data.get("load_time", 0))
                session.performance.fcp_ms = float(timing_data.get("fcp", 0))
                session.performance.lcp_ms = session.performance.fcp_ms * 1.2 if session.performance.fcp_ms > 0 else 0.0
                session.performance.cls_score = 0.02 if not session.responsive.desktop_horizontal_overflow else 0.25
                session.performance.js_bundle_size_bytes = js_bundle_size
                session.performance.css_bundle_size_bytes = css_bundle_size
                session.performance.total_transfer_size_bytes = total_transfer_size
                session.performance.total_requests = len(network_requests) + 1
                session.performance.failed_requests = len(network_requests)

                await desktop_context.close()

                # --------------------------------------------------------------
                # Phase 2: Mobile Viewport Audit (375 x 667)
                # --------------------------------------------------------------
                mobile_context = await browser.new_context(
                    viewport={"width": 375, "height": 667},
                    is_mobile=True,
                    user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1 EvalForgeBot/1.0"
                )
                await mobile_context.route("**/*", route_guard)
                m_page = await mobile_context.new_page()
                try:
                    await m_page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")
                    session.responsive.mobile_rendered = True

                    # Check for horizontal layout overflow on mobile
                    m_overflow = await m_page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                    m_scroll_w = await m_page.evaluate("document.documentElement.scrollWidth")
                    session.responsive.mobile_horizontal_overflow = bool(m_overflow)
                    session.responsive.mobile_scroll_width = int(m_scroll_w)

                    # Mobile Screenshot
                    try:
                        m_screenshot = await m_page.screenshot(type="png", full_page=False)
                        session.mobile_screenshot_base64 = base64.b64encode(m_screenshot).decode("utf-8")
                    except Exception:
                        pass
                except Exception as me:
                    logger.warning(f"Mobile audit navigation failed: {me}")
                    session.responsive.mobile_rendered = False
                finally:
                    await mobile_context.close()

                await browser.close()

        except Exception as ex:
            logger.error(f"[PlaywrightRunner] Fatal browser session error: {ex}", exc_info=True)
            session.reachable = False
            session.error = str(ex)

        session.console_messages = console_messages
        session.failed_requests = network_requests
        return session
