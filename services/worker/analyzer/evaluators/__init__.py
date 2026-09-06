from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from .problem_analyzer import ProblemAnalyzer
from .solution_analyzer import SolutionAnalyzer
from .code_quality import CodeQualityAnalyzer
from .optimization import OptimizationAnalyzer
from .ui_analyzer import UIAnalyzer
from .performance import PerformanceAnalyzer
from .security import SecurityAnalyzer
from .novelty import NoveltyAnalyzer
from .documentation import DocumentationAnalyzer
from .engineering import EngineeringAnalyzer
from typing import List

def get_standard_evaluators() -> List[BaseEvaluator]:
    """Returns initialized instances of all 10 standard EvalForge evaluators."""
    return [
        ProblemAnalyzer(),
        SolutionAnalyzer(),
        CodeQualityAnalyzer(),
        OptimizationAnalyzer(),
        UIAnalyzer(),
        PerformanceAnalyzer(),
        SecurityAnalyzer(),
        NoveltyAnalyzer(),
        DocumentationAnalyzer(),
        EngineeringAnalyzer(),
    ]

__all__ = [
    "BaseEvaluator",
    "EvaluationResult",
    "EvidenceItem",
    "ProblemAnalyzer",
    "SolutionAnalyzer",
    "CodeQualityAnalyzer",
    "OptimizationAnalyzer",
    "UIAnalyzer",
    "PerformanceAnalyzer",
    "SecurityAnalyzer",
    "NoveltyAnalyzer",
    "DocumentationAnalyzer",
    "EngineeringAnalyzer",
    "get_standard_evaluators"
]
