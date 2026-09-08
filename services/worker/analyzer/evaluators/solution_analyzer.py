import logging
from typing import Dict, List, Optional
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact
from ..rubrics import (
    SolutionRubricEvaluation,
    calculate_solution_score,
    SOLUTION_DIMENSION_WEIGHTS
)
from ..llm.context_packer import ContextPacker
from ..llm.client import BaseLLMClient, get_llm_client, LLMMalformedResponseError

logger = logging.getLogger("evalforge.evaluators.solution_analyzer")

RUBRIC_VERSION = "1.0.0"
EVALUATOR_VERSION = "1.0.0"

class SolutionAnalyzer(BaseEvaluator):
    """
    Evaluates solution quality, technical architecture, and feasibility using structured LLM rubric evaluation.
    Dimensions: correctness (2.5), relevance_to_problem (2.5), architecture (2.5), feasibility (2.0),
    completeness (2.0), technical_reasoning (2.0), and trade_offs (1.5).
    Max Score: 15.0
    Dependencies: ProblemAnalyzer
    """
    def __init__(self, llm_client: Optional[BaseLLMClient] = None, timeout_seconds: float = 30.0):
        super().__init__(
            name="SolutionAnalyzer",
            criterion="solution_quality",
            max_score=15.0,
            dependencies=["ProblemAnalyzer"],
            timeout_seconds=timeout_seconds
        )
        self.llm_client = llm_client or get_llm_client()

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        # 1. Retrieve ProblemAnalyzer context
        problem_res = context.get("ProblemAnalyzer")
        problem_context = {
            "score": problem_res.score if problem_res else 0.0,
            "summary": problem_res.summary if problem_res else "Problem statement evaluation unavailable."
        } if problem_res else None

        # 2. Pack context from repository and submission metadata
        packed_context = ContextPacker.pack_context(artifact)

        # 3. Invoke structured LLM evaluation with retry/rejection handling
        try:
            rubric_eval: SolutionRubricEvaluation = self.llm_client.evaluate_solution(
                context=packed_context,
                problem_context=problem_context,
                max_retries=2
            )
        except LLMMalformedResponseError as mre:
            logger.error(f"[SolutionAnalyzer] LLM malformed response rejected: {mre}")
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

        # 4. Deterministically compute final score from dimension weights
        final_score, breakdown = calculate_solution_score(rubric_eval)

        # 5. Generate dimension evidence items with citations and anti-fabrication tracking
        evidence_items: List[EvidenceItem] = []
        known_files = set(artifact.file_tree)

        for dim_name in SOLUTION_DIMENSION_WEIGHTS:
            dim_obj = getattr(rubric_eval, dim_name)

            # Validate citations against known files or submission metadata
            validated_citations = []
            for c in dim_obj.citations:
                c_clean = c.split(":")[0].strip()
                if c_clean in known_files or c_clean.lower() in ["readme.md", "package.json", "architecture"]:
                    validated_citations.append({"citation": c, "verified": True})
                else:
                    validated_citations.append({"citation": c, "verified": False, "note": "Unverified reference"})

            evidence_items.append(EvidenceItem(
                source="solution_rubric",
                metric=f"dimension_{dim_name}",
                value=round(dim_obj.score, 2),
                interpretation=dim_obj.reasoning,
                raw_data={
                    "dimension": dim_name,
                    "raw_score": dim_obj.score,
                    "weighted_score": breakdown.get(dim_name, 0.0),
                    "max_weight": SOLUTION_DIMENSION_WEIGHTS[dim_name],
                    "citations": validated_citations
                },
                citation_reference={"citations": dim_obj.citations} if dim_obj.citations else None
            ))

        # 6. Attach evaluation metadata evidence
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

        confidence = 0.90 if artifact.file_tree and artifact.has_readme else 0.70

        summary = (
            f"Solution architecture scored {final_score:.1f}/{self.max_score} "
            f"(Correctness: {breakdown['correctness']:.1f}/2.5, Relevance: {breakdown['relevance_to_problem']:.1f}/2.5, "
            f"Architecture: {breakdown['architecture']:.1f}/2.5, Feasibility: {breakdown['feasibility']:.1f}/2.0, "
            f"Completeness: {breakdown['completeness']:.1f}/2.0, Reasoning: {breakdown['technical_reasoning']:.1f}/2.0, "
            f"Trade-offs: {breakdown['trade_offs']:.1f}/1.5)."
        )

        return EvaluationResult(
            criterion=self.criterion,
            score=final_score,
            maxScore=self.max_score,
            confidence=confidence,
            summary=summary,
            strengths=rubric_eval.strengths or ["Solution demonstrates modular design."],
            weaknesses=rubric_eval.weaknesses,
            recommendations=rubric_eval.recommendations or ["Document architectural decisions in ADRs."],
            evidence=evidence_items
        )
