from __future__ import annotations
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, TYPE_CHECKING
from datetime import datetime, timezone

if TYPE_CHECKING:
    from ..evaluators.base import EvaluationResult

logger = logging.getLogger("evalforge.aggregator")

# Standard Rubric v1.0.0 Category Definitions (Strictly Summing to 100.00)
DEFAULT_RUBRIC_V1: Dict[str, Dict[str, Any]] = {
    "problem_statement": {
        "name": "Problem Statement",
        "evaluator": "ProblemAnalyzer",
        "weight": 10.0,
        "max_score": 10.0,
        "description": "Clarity, real-world relevance, scope definition, and target audience alignment."
    },
    "solution_quality": {
        "name": "Solution Quality",
        "evaluator": "SolutionAnalyzer",
        "weight": 15.0,
        "max_score": 15.0,
        "description": "Soundness of technical architecture, system design, domain modeling, and tech stack."
    },
    "code_quality": {
        "name": "Code Quality",
        "evaluator": "CodeQualityAnalyzer",
        "weight": 15.0,
        "max_score": 15.0,
        "description": "Deterministic syntax conformance, formatting consistency, AST complexity, and static analysis."
    },
    "optimization": {
        "name": "Optimization",
        "evaluator": "OptimizationAnalyzer",
        "weight": 10.0,
        "max_score": 10.0,
        "description": "Resource efficiency, memory management, bundle size awareness, and algorithmic complexity."
    },
    "ui_ux": {
        "name": "UI/UX",
        "evaluator": "UIAnalyzer",
        "weight": 10.0,
        "max_score": 10.0,
        "description": "Visual polish, responsive viewports, design system consistency, and accessibility."
    },
    "performance": {
        "name": "Performance",
        "evaluator": "PerformanceAnalyzer",
        "weight": 10.0,
        "max_score": 10.0,
        "description": "Empirical Core Web Vitals, server response times (TTFB), and Lighthouse performance audit."
    },
    "security": {
        "name": "Security",
        "evaluator": "SecurityAnalyzer",
        "weight": 10.0,
        "max_score": 10.0,
        "description": "Static vulnerability scanning (SAST), dependency CVE audits, secret leakage detection."
    },
    "novelty": {
        "name": "Innovation/Novelty",
        "evaluator": "NoveltyAnalyzer",
        "weight": 5.0,
        "max_score": 5.0,
        "description": "Originality of technical approach, differentiation from existing solutions, and verified market novelty."
    },
    "documentation": {
        "name": "Documentation",
        "evaluator": "DocumentationAnalyzer",
        "weight": 5.0,
        "max_score": 5.0,
        "description": "Completeness of README, architecture diagrams, local setup instructions, and inline comments."
    },
    "engineering_practices": {
        "name": "Engineering Practices",
        "evaluator": "EngineeringAnalyzer",
        "weight": 10.0,
        "max_score": 10.0,
        "description": "CI/CD pipeline presence, automated test coverage, environment configuration hygiene."
    }
}

@dataclass
class CategoryScoreBreakdown:
    category_key: str
    category_name: str
    evaluator_name: str
    raw_score: float
    max_score: float
    weight: float
    normalized_score: float
    confidence: float
    status: str  # 'measured', 'unmeasurable', 'failed', 'missing'
    summary: str
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category_key": self.category_key,
            "category_name": self.category_name,
            "evaluator_name": self.evaluator_name,
            "raw_score": self.raw_score,
            "max_score": self.max_score,
            "weight": self.weight,
            "normalized_score": self.normalized_score,
            "confidence": self.confidence,
            "status": self.status,
            "summary": self.summary,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "recommendations": self.recommendations,
        }

@dataclass
class AggregatedScoreReport:
    rubric_version: str
    overall_score: float
    confidence: float
    total_possible_weight: float
    weights_snapshot: Dict[str, float]
    score_breakdown: Dict[str, Dict[str, Any]]
    executive_summary: str
    key_strengths: List[str]
    key_weaknesses: List[str]
    action_plan: List[str]
    similar_projects: List[Dict[str, Any]]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rubric_version": self.rubric_version,
            "overall_score": self.overall_score,
            "confidence": self.confidence,
            "total_possible_weight": self.total_possible_weight,
            "weights_snapshot": self.weights_snapshot,
            "score_breakdown": self.score_breakdown,
            "executive_summary": self.executive_summary,
            "key_strengths": self.key_strengths,
            "key_weaknesses": self.key_weaknesses,
            "action_plan": self.action_plan,
            "similar_projects": self.similar_projects,
            "created_at": self.created_at,
        }

class ScoreAggregator:
    """
    Deterministic score aggregator for EvalForge evaluations.
    Applies strict mathematical weights, handles unmeasurable/missing evaluators transparently,
    and constructs reproducible evaluation reports without LLM hallucinations.
    """
    def __init__(self, rubric_version: str = "1.0.0", custom_rubric: Optional[Dict[str, Dict[str, Any]]] = None):
        self.rubric_version = rubric_version
        self.rubric = custom_rubric or DEFAULT_RUBRIC_V1
        self._validate_rubric_weights()

    def _validate_rubric_weights(self):
        """Ensure rubric weights sum to exactly 100.00."""
        total_weight = sum(cat["weight"] for cat in self.rubric.values())
        if abs(total_weight - 100.00) > 0.01:
            raise ValueError(f"Rubric {self.rubric_version} category weights sum to {total_weight}, expected 100.00.")

    def aggregate(
        self,
        evaluator_results: Dict[str, EvaluationResult],
        project_name: str = "Project"
    ) -> AggregatedScoreReport:
        """
        Deterministically calculate final weighted score and compile report artifact.
        """
        breakdowns: Dict[str, CategoryScoreBreakdown] = {}
        total_normalized_score = 0.0
        weighted_confidence_sum = 0.0
        all_strengths: List[str] = []
        all_weaknesses: List[str] = []
        all_recommendations: List[str] = []
        similar_projects: List[Dict[str, Any]] = []

        # Invert map: evaluator_name -> category_key
        eval_to_cat = {cat["evaluator"]: key for key, cat in self.rubric.items()}

        for cat_key, cat_def in self.rubric.items():
            eval_name = cat_def["evaluator"]
            weight = float(cat_def["weight"])
            max_cat_score = float(cat_def["max_score"])

            res: Optional[EvaluationResult] = evaluator_results.get(eval_name)

            if res is None:
                # Missing evaluator: Explicitly handle without awarding unearned points
                logger.warning(f"Evaluator '{eval_name}' was not run for category '{cat_key}'.")
                breakdowns[cat_key] = CategoryScoreBreakdown(
                    category_key=cat_key,
                    category_name=cat_def["name"],
                    evaluator_name=eval_name,
                    raw_score=0.0,
                    max_score=max_cat_score,
                    weight=weight,
                    normalized_score=0.0,
                    confidence=0.0,
                    status="missing",
                    summary="Evaluator was not executed for this category.",
                    strengths=[],
                    weaknesses=[f"No evaluation results available for {cat_def['name']}."],
                    recommendations=[f"Run {eval_name} to assess {cat_def['name']}."]
                )
                continue

            # Validate bounds
            raw_score = max(0.0, min(float(res.score), float(res.maxScore)))
            res_max = max(0.01, float(res.maxScore))
            confidence = max(0.0, min(1.0, float(res.confidence)))

            # Check for unmeasurable / failed
            is_unmeasurable = "not measurable" in (res.summary or "").lower() or any(
                e.metric == "live_url_metrics" and e.value == "unmeasurable" for e in res.evidence
            )

            # Normalization: (raw_score / res_max) * weight
            normalized = round((raw_score / res_max) * weight, 2)
            normalized = min(normalized, weight)

            status = "unmeasurable" if is_unmeasurable and raw_score == 0.0 else "measured"

            bd = CategoryScoreBreakdown(
                category_key=cat_key,
                category_name=cat_def["name"],
                evaluator_name=eval_name,
                raw_score=raw_score,
                max_score=res_max,
                weight=weight,
                normalized_score=normalized,
                confidence=confidence,
                status=status,
                summary=res.summary or f"{cat_def['name']} evaluated.",
                strengths=res.strengths or [],
                weaknesses=res.weaknesses or [],
                recommendations=res.recommendations or []
            )
            breakdowns[cat_key] = bd

            total_normalized_score += normalized
            weighted_confidence_sum += (confidence * (weight / 100.0))

            all_strengths.extend(res.strengths or [])
            all_weaknesses.extend(res.weaknesses or [])
            all_recommendations.extend(res.recommendations or [])

            # Extract similar projects citations from novelty evaluator if present
            if eval_name == "NoveltyAnalyzer":
                for ev in res.evidence:
                    if ev.citation_reference and isinstance(ev.citation_reference, dict):
                        similar_projects.append(ev.citation_reference)

        final_overall_score = round(min(100.0, max(0.0, total_normalized_score)), 2)
        final_confidence = round(min(1.0, max(0.0, weighted_confidence_sum)), 3)

        # Generate grounded executive summary
        if final_overall_score >= 85.0:
            rating_label = "Production Ready / Exemplary"
        elif final_overall_score >= 70.0:
            rating_label = "Strong / Competent Engineering"
        elif final_overall_score >= 50.0:
            rating_label = "Adequate / Needs Hardening"
        else:
            rating_label = "Deficient / High Risk"

        exec_summary = (
            f"Overall evaluation score: {final_overall_score:.1f}/100 ({rating_label}) "
            f"with {final_confidence * 100:.1f}% confidence across 10 deterministic and qualitative criteria. "
            f"Identified {len(all_strengths)} engineering strengths and {len(all_weaknesses)} areas for improvement."
        )

        weights_snapshot = {k: v["weight"] for k, v in self.rubric.items()}
        score_breakdown_dict = {k: v.to_dict() for k, v in breakdowns.items()}

        return AggregatedScoreReport(
            rubric_version=self.rubric_version,
            overall_score=final_overall_score,
            confidence=final_confidence,
            total_possible_weight=100.00,
            weights_snapshot=weights_snapshot,
            score_breakdown=score_breakdown_dict,
            executive_summary=exec_summary,
            key_strengths=all_strengths[:8],  # Curate top key items
            key_weaknesses=all_weaknesses[:8],
            action_plan=all_recommendations[:8],
            similar_projects=similar_projects,
            created_at=datetime.now(timezone.utc).isoformat()
        )
