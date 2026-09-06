from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

@dataclass
class ConsoleMessageAudit:
    type: str  # "error", "warning", "log", "info"
    text: str
    location: Optional[str] = None

@dataclass
class NetworkRequestAudit:
    url: str
    method: str
    status: int
    failed: bool
    failure_text: Optional[str] = None
    duration_ms: float = 0.0
    size_bytes: int = 0
    content_type: Optional[str] = None

@dataclass
class ResponsiveAudit:
    desktop_rendered: bool = False
    desktop_width: int = 1280
    desktop_height: int = 800
    mobile_rendered: bool = False
    mobile_width: int = 375
    mobile_height: int = 667
    mobile_horizontal_overflow: bool = False
    mobile_scroll_width: int = 0
    desktop_horizontal_overflow: bool = False
    desktop_scroll_width: int = 0

@dataclass
class FormFieldDetail:
    tag: str
    input_type: Optional[str] = None
    name: Optional[str] = None
    has_label: bool = False
    required: bool = False

@dataclass
class FormAudit:
    action: Optional[str] = None
    method: str = "GET"
    fields: List[FormFieldDetail] = field(default_factory=list)
    has_submit_button: bool = False

@dataclass
class InteractiveAudit:
    button_count: int = 0
    link_count: int = 0
    form_count: int = 0
    input_count: int = 0
    forms: List[FormAudit] = field(default_factory=list)
    sample_interactive_labels: List[str] = field(default_factory=list)

@dataclass
class AccessibilityAudit:
    total_images: int = 0
    images_with_alt: int = 0
    images_missing_alt: List[str] = field(default_factory=list)
    total_inputs: int = 0
    inputs_with_labels: int = 0
    inputs_missing_labels: List[str] = field(default_factory=list)
    has_title: bool = False
    page_title: Optional[str] = None
    has_lang: bool = False
    lang_code: Optional[str] = None
    heading_counts: Dict[str, int] = field(default_factory=dict)
    violations_count: int = 0
    violations_summary: List[str] = field(default_factory=list)

@dataclass
class PerformanceMetrics:
    ttfb_ms: float = 0.0
    fcp_ms: float = 0.0
    lcp_ms: float = 0.0
    cls_score: float = 0.0
    dom_content_loaded_ms: float = 0.0
    load_time_ms: float = 0.0
    total_requests: int = 0
    failed_requests: int = 0
    js_bundle_size_bytes: int = 0
    css_bundle_size_bytes: int = 0
    total_transfer_size_bytes: int = 0
    lighthouse_performance_score: Optional[float] = None
    lighthouse_accessibility_score: Optional[float] = None
    lighthouse_best_practices_score: Optional[float] = None
    lighthouse_seo_score: Optional[float] = None

@dataclass
class BrowserSessionResult:
    url: str
    reachable: bool = False
    http_status: int = 0
    error: Optional[str] = None
    responsive: ResponsiveAudit = field(default_factory=ResponsiveAudit)
    interactive: InteractiveAudit = field(default_factory=InteractiveAudit)
    accessibility: AccessibilityAudit = field(default_factory=AccessibilityAudit)
    performance: PerformanceMetrics = field(default_factory=PerformanceMetrics)
    console_messages: List[ConsoleMessageAudit] = field(default_factory=list)
    failed_requests: List[NetworkRequestAudit] = field(default_factory=list)
    desktop_screenshot_base64: Optional[str] = None
    mobile_screenshot_base64: Optional[str] = None
