import json
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from .sandbox import scrub_secrets

class StructuredLogger:
    """
    Structured JSON logger for EvalForge worker operations.
    Emits standardized telemetry records for runs, evaluators, and system errors.
    Automatically scrubs secrets from all logged values.
    """
    def __init__(self, logger_name: str = "evalforge.observability"):
        self.logger = logging.getLogger(logger_name)

    def log_evaluation_event(
        self,
        evaluation_run_id: str,
        worker_id: str,
        evaluator: Optional[str] = None,
        duration_ms: Optional[float] = None,
        status: str = "completed",
        error_category: Optional[str] = None,
        message: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "evaluation_run_id": evaluation_run_id,
            "worker_id": worker_id,
            "evaluator": evaluator,
            "duration_ms": round(duration_ms, 2) if duration_ms is not None else None,
            "status": status,
            "error_category": error_category,
            "message": scrub_secrets(message) if message else None,
            "extra": {k: scrub_secrets(str(v)) if isinstance(v, str) else v for k, v in (extra or {}).items()}
        }

        # Filter out None fields for clean logs
        cleaned = {k: v for k, v in record.items() if v is not None}
        log_line = json.dumps(cleaned)

        if status in ("failed", "error") or error_category:
            self.logger.error(log_line)
        elif status == "warning":
            self.logger.warning(log_line)
        else:
            self.logger.info(log_line)

structured_logger = StructuredLogger()
