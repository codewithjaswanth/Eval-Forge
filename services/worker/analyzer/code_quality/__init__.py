"""
Deterministic Code Quality Analysis Suite for EvalForge.
Provides empirical measurements for syntax, linting, formatting, type safety,
test coverage discovery, package metadata hygiene, file structure, and dead code.
"""

from .linters import analyze_linting_and_formatting, LintAnalysisResult
from .types import analyze_type_safety, TypeSafetyResult
from .tests_runner import analyze_tests, TestAnalysisResult
from .packages import analyze_package_metadata, PackageAnalysisResult
from .structure import analyze_file_structure, StructureAnalysisResult

__all__ = [
    "analyze_linting_and_formatting",
    "LintAnalysisResult",
    "analyze_type_safety",
    "TypeSafetyResult",
    "analyze_tests",
    "TestAnalysisResult",
    "analyze_package_metadata",
    "PackageAnalysisResult",
    "analyze_file_structure",
    "StructureAnalysisResult"
]
