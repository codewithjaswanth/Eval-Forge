from typing import Dict, Tuple
from .models import ProblemRubricEvaluation, SolutionRubricEvaluation

PROBLEM_DIMENSION_WEIGHTS: Dict[str, float] = {
    "clarity": 2.0,
    "specificity": 2.0,
    "importance": 1.5,
    "affected_users": 1.5,
    "constraints": 1.5,
    "evidence_of_understanding": 1.5
}

SOLUTION_DIMENSION_WEIGHTS: Dict[str, float] = {
    "correctness": 2.5,
    "relevance_to_problem": 2.5,
    "architecture": 2.5,
    "feasibility": 2.0,
    "completeness": 2.0,
    "technical_reasoning": 2.0,
    "trade_offs": 1.5
}

def calculate_problem_score(evaluation: ProblemRubricEvaluation) -> Tuple[float, Dict[str, float]]:
    """
    Deterministically computes category score for ProblemAnalyzer from dimension scores.
    Returns (total_score_out_of_10, breakdown_dict).
    """
    breakdown = {}
    total = 0.0

    for dim_name, weight in PROBLEM_DIMENSION_WEIGHTS.items():
        dim_obj = getattr(evaluation, dim_name)
        dim_score = max(0.0, min(1.0, float(dim_obj.score)))
        weighted = round(dim_score * weight, 2)
        breakdown[dim_name] = weighted
        total += weighted

    total_score = round(min(10.0, max(0.0, total)), 2)
    return total_score, breakdown

def calculate_solution_score(evaluation: SolutionRubricEvaluation) -> Tuple[float, Dict[str, float]]:
    """
    Deterministically computes category score for SolutionAnalyzer from dimension scores.
    Returns (total_score_out_of_15, breakdown_dict).
    """
    breakdown = {}
    total = 0.0

    for dim_name, weight in SOLUTION_DIMENSION_WEIGHTS.items():
        dim_obj = getattr(evaluation, dim_name)
        dim_score = max(0.0, min(1.0, float(dim_obj.score)))
        weighted = round(dim_score * weight, 2)
        breakdown[dim_name] = weighted
        total += weighted

    total_score = round(min(15.0, max(0.0, total)), 2)
    return total_score, breakdown
