import abc
import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from ..models import ProjectArtifact

logger = logging.getLogger("evalforge.evaluator")

@dataclass
class EvidenceItem:
    """Standard evidence record substantiating an objective or qualitative finding."""
    source: str
    metric: str
    value: Any
    interpretation: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_data: Dict[str, Any] = field(default_factory=dict)
    citation_reference: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "metric": self.metric,
            "value": self.value,
            "interpretation": self.interpretation,
            "timestamp": self.timestamp,
            "raw_data": self.raw_data,
            "citation_reference": self.citation_reference
        }

@dataclass
class EvaluationResult:
    """Standard evaluation result contract returned by every EvalForge evaluator."""
    criterion: str
    score: float
    maxScore: float
    confidence: float
    summary: str
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    evidence: List[EvidenceItem] = field(default_factory=list)
    is_error: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "criterion": self.criterion,
            "score": round(self.score, 2),
            "maxScore": round(self.maxScore, 2),
            "confidence": round(self.confidence, 3),
            "summary": self.summary,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "recommendations": self.recommendations,
            "evidence": [e.to_dict() for e in self.evidence]
        }

class BaseEvaluator(abc.ABC):
    """
    Abstract base evaluator for all EvalForge analysis modules.
    Provides structured result contracts, execution isolation, timeouts, and validation.
    """
    def __init__(
        self,
        name: str,
        criterion: str,
        max_score: float,
        dependencies: Optional[List[str]] = None,
        timeout_seconds: float = 30.0
    ):
        self.name = name
        self.criterion = criterion
        self.max_score = max_score
        self.dependencies = dependencies or []
        self.timeout_seconds = timeout_seconds

    @abc.abstractmethod
    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        """
        Execute core evaluator analysis logic.
        Receives the ingested ProjectArtifact and a map of completed dependency results.
        """
        pass

    def validate(self, result: EvaluationResult) -> bool:
        """Validate that the evaluator result conforms strictly to the system contract."""
        if not isinstance(result, EvaluationResult):
            return False
        if result.criterion != self.criterion:
            logger.error(f"[{self.name}] Criterion mismatch: expected {self.criterion}, got {result.criterion}")
            return False
        if result.score < 0 or result.score > result.maxScore:
            logger.error(f"[{self.name}] Invalid score {result.score} (max {result.maxScore})")
            return False
        if result.confidence < 0.0 or result.confidence > 1.0:
            logger.error(f"[{self.name}] Invalid confidence {result.confidence}")
            return False
        if not result.summary:
            logger.error(f"[{self.name}] Missing summary in result")
            return False
        return True

    async def run_safe(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        """
        Safe execution harness applying timeouts, error catching, and contract validation.
        """
        logger.info(f"[{self.name}] Running evaluation (timeout: {self.timeout_seconds}s)...")
        start_time = time.monotonic()
        try:
            result = await asyncio.wait_for(
                self.execute(artifact, context),
                timeout=self.timeout_seconds
            )
            duration = time.monotonic() - start_time
            logger.info(f"[{self.name}] Completed in {duration:.2f}s (Score: {result.score}/{result.maxScore})")

            if not self.validate(result):
                err = f"Evaluator result validation failed for {self.name}"
                logger.error(f"[{self.name}] {err}")
                return EvaluationResult(
                    criterion=self.criterion,
                    score=0.0,
                    maxScore=self.max_score,
                    confidence=0.0,
                    summary=f"Evaluation failed due to contract validation failure: {err}",
                    weaknesses=[err],
                    recommendations=["Ensure evaluator output satisfies standard contract."],
                    is_error=True,
                    error_message=err
                )

            return result

        except asyncio.TimeoutError:
            duration = time.monotonic() - start_time
            err = f"Evaluation timed out after {self.timeout_seconds}s"
            logger.error(f"[{self.name}] {err}")
            return EvaluationResult(
                criterion=self.criterion,
                score=0.0,
                maxScore=self.max_score,
                confidence=0.0,
                summary=f"Evaluator timed out: {err}",
                weaknesses=[err],
                recommendations=["Optimize execution speed or check for network stalls."],
                evidence=[
                    EvidenceItem(
                        source=self.name,
                        metric="timeout",
                        value=self.timeout_seconds,
                        interpretation="Evaluator execution exceeded maximum allowable timeout."
                    )
                ],
                is_error=True,
                error_message=err
            )
        except Exception as e:
            duration = time.monotonic() - start_time
            err = f"Evaluator execution error: {str(e)}"
            logger.error(f"[{self.name}] {err}", exc_info=True)
            return EvaluationResult(
                criterion=self.criterion,
                score=0.0,
                maxScore=self.max_score,
                confidence=0.0,
                summary=f"Evaluation failed due to internal error: {str(e)}",
                weaknesses=[err],
                recommendations=["Check module logs and dependencies."],
                evidence=[
                    EvidenceItem(
                        source=self.name,
                        metric="execution_error",
                        value=str(e),
                        interpretation="Exception caught during evaluator execution."
                    )
                ],
                is_error=True,
                error_message=err
            )
