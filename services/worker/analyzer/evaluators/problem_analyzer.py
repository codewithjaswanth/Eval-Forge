import logging
from typing import Dict, List, Optional
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact
from ..rubrics import (
    ProblemRubricEvaluation,
    calculate_problem_score,
    PROBLEM_DIMENSION_WEIGHTS
)
from ..llm import ContextPacker, BaseLLMClient, get_llm_client, LLMMalformedResponseError

logger = logging.getLogger("evalforge.evaluators.problem_analyzer")

RUBRIC_VERSION = "1.0.0"
EVALUATOR_VERSION = "1.0.0"

class ProblemAnalyzer(BaseEvaluator):
    """
    Evaluates problem statement quality using structured LLM rubric evaluation.
    Dimensions: clarity (2.0), specificity (2.0), importance (1.5), affected_users (1.5),
    constraints (1.5), and evidence_of_understanding (1.5).
    Max Score: 10.0
    Dependencies: None
    """
    def __init__(self, llm_client: Optional[BaseLLMClient] = None, timeout_seconds: float = 30.0):
        super().__init__(
            name="ProblemAnalyzer",
            criterion="problem_statement",
            max_score=10.0,
            dependencies=[],
            timeout_seconds=timeout_seconds
        )
        self.llm_client = llm_client or get_llm_client()

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        # 1. Pack context from repository and submission metadata
        packed_context = ContextPacker.pack_context(artifact)

        # 2. Invoke structured LLM evaluation with retry/rejection handling
        try:
            rubric_eval: ProblemRubricEvaluation = self.llm_client.evaluate_problem(
                context=packed_context,
                max_retries=2
            )
        except LLMMalformedResponseError as mre:
            logger.error(f"[ProblemAnalyzer] LLM malformed response rejected: {mre}")
            return EvaluationResult(
                criterion=self.criterion,
                score=0.0,
                maxScore=self.max_score,
                confidence=0.0,
                summary=f"Evaluation failed: Malformed LLM response rejected: {mre}",
                weaknesses=["LLM output failed strict schema validation and was rejected."],
                recommendations=["Check evaluation prompt and model JSON generation."],
                is_error=True,
                error_message=str(mre)
            )

        # 3. Deterministically compute final score from dimension weights
        final_score, breakdown = calculate_problem_score(rubric_eval)

        # 4. Generate dimension evidence items with citations and anti-fabrication tracking
        evidence_items: List[EvidenceItem] = []
        known_files = set(artifact.file_tree)

        for dim_name in PROBLEM_DIMENSION_WEIGHTS:
            dim_obj = getattr(rubric_eval, dim_name)
            
            # Validate citations against known files or submission metadata
            validated_citations = []
            for c in dim_obj.citations:
                c_clean = c.split(":")[0].strip()
                if c_clean in known_files or c_clean.lower() in ["readme.md", "project description", "architecture"]:
                    validated_citations.append({"citation": c, "verified": True})
                else:
                    validated_citations.append({"citation": c, "verified": False, "note": "Unverified reference"})

            evidence_items.append(EvidenceItem(
                source="problem_rubric",
                metric=f"dimension_{dim_name}",
                value=round(dim_obj.score, 2),
                interpretation=dim_obj.reasoning,
                raw_data={
                    "dimension": dim_name,
                    "raw_score": dim_obj.score,
                    "weighted_score": breakdown.get(dim_name, 0.0),
                    "max_weight": PROBLEM_DIMENSION_WEIGHTS[dim_name],
                    "citations": validated_citations
                },
                citation_reference={"citations": dim_obj.citations} if dim_obj.citations else None
            ))

        # 5. Attach evaluation metadata evidence
        evidence_items.append(EvidenceItem(
            source="evaluation_engine",
            metric="evaluation_metadata",
            value="grounded_rubric",
            interpretation=f"Evaluated with model {self.llm_client.model_name}, rubric v{RUBRIC_VERSION}.",
            raw_data={
                "model_name": self.llm_client.model_name,
                "rubric_version": RUBRIC_VERSION,
                "evaluator_version": EVALUATOR_VERSION,
                "breakdown": breakdown
            }
        ))

        # 6. Confidence based on context completeness
        confidence = 0.90 if artifact.description and artifact.has_readme else (
            0.75 if artifact.description or artifact.has_readme else 0.50
        )

        summary = (
            f"Problem statement scored {final_score:.1f}/{self.max_score} "
            f"(Clarity: {breakdown['clarity']:.1f}/2.0, Specificity: {breakdown['specificity']:.1f}/2.0, "
            f"Importance: {breakdown['importance']:.1f}/1.5, Users: {breakdown['affected_users']:.1f}/1.5, "
            f"Constraints: {breakdown['constraints']:.1f}/1.5, Understanding: {breakdown['evidence_of_understanding']:.1f}/1.5)."
        )

        return EvaluationResult(
            criterion=self.criterion,
            score=final_score,
            maxScore=self.max_score,
            confidence=confidence,
            summary=summary,
            strengths=rubric_eval.strengths or ["Problem statement is clearly documented."],
            weaknesses=rubric_eval.weaknesses,
            recommendations=rubric_eval.recommendations or ["Continue refining problem boundaries."],
            evidence=evidence_items
        )
