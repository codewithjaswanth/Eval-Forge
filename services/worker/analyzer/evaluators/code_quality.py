import logging
from typing import Dict, List
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact
from ..code_quality import (
    analyze_linting_and_formatting,
    analyze_type_safety,
    analyze_tests,
    analyze_package_metadata,
    analyze_file_structure
)

logger = logging.getLogger("evalforge.evaluators.code_quality")

class CodeQualityAnalyzer(BaseEvaluator):
    """
    Deterministic Code-Quality Evaluation Engine.
    Executes multi-stack static analysis, type checking, test discovery,
    package manifest audits, and file tree structure checks without an LLM.
    Max Score: 15.0
    Dependencies: None
    """
    def __init__(self, timeout_seconds: float = 30.0):
        super().__init__(
            name="CodeQualityAnalyzer",
            criterion="code_quality",
            max_score=15.0,
            dependencies=[],
            timeout_seconds=timeout_seconds
        )

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        evidence: List[EvidenceItem] = []
        strengths: List[str] = []
        weaknesses: List[str] = []
        recommendations: List[str] = []

        measurable_dimensions = 0
        total_dimensions = 5

        # ----------------------------------------------------------------------
        # 1. Static Analysis & Linting / Formatting
        # ----------------------------------------------------------------------
        lint_res = await analyze_linting_and_formatting(
            root_path=artifact.root_path,
            file_tree=artifact.file_tree,
            detected_languages=artifact.detected_languages,
            config_files=artifact.config_files,
            timeout_seconds=min(30.0, self.timeout_seconds)
        )

        lint_pts = 0.0
        if lint_res.measurable:
            measurable_dimensions += (1.0 if lint_res.tool_real else 0.6)
            base = 3.5 if lint_res.linter_config_present else 2.0
            if lint_res.formatter_config_present:
                base += 0.5
            penalties = (lint_res.errors_count * 1.0) + (lint_res.warnings_count * 0.1) + (lint_res.formatting_violations_count * 0.2)
            lint_pts = max(0.0, min(4.0, base - penalties))

            if lint_res.tool_real:
                strengths.append(f"Real static analysis active ({lint_res.linter_name}).")
            elif lint_res.linter_config_present:
                strengths.append(f"Static linter configured: {lint_res.linter_name}")
            else:
                weaknesses.append("Missing explicit linter configuration file (e.g. ESLint / Ruff).")
                recommendations.append("Adopt an automated linter configuration to enforce consistent code standards.")

            if not lint_res.tool_real and lint_res.linter_config_present:
                weaknesses.append(f"Real linter binary unavailable ({lint_res.linter_name}); fell back to heuristic static analysis.")

            if lint_res.errors_count > 0:
                weaknesses.append(f"Detected {lint_res.errors_count} syntax/linter error(s).")
                recommendations.append("Resolve syntax and static analysis errors.")
            elif lint_res.linter_config_present and lint_res.tool_real:
                strengths.append("Zero syntax or parsing errors detected across scanned files.")

            lint_interpretation = (
                f"Real static analysis ({lint_res.tool_used}): Found {lint_res.errors_count} syntax/lint error(s)."
                if lint_res.tool_real
                else f"Heuristic static analysis ({lint_res.tool_used} fallback): Found {lint_res.errors_count} syntax/lint error(s). Real linter unavailable."
            )
            evidence.append(EvidenceItem(
                source="linter_analysis",
                metric="lint_errors",
                value=lint_res.errors_count,
                interpretation=lint_interpretation,
                raw_data={"issues": lint_res.issues[:10], "tool_used": lint_res.tool_used, "tool_real": lint_res.tool_real}
            ))
            evidence.append(EvidenceItem(
                source="linter_analysis",
                metric="lint_warnings",
                value=lint_res.warnings_count,
                interpretation=f"Found {lint_res.warnings_count} linter warning(s)."
            ))
            evidence.append(EvidenceItem(
                source="formatter_analysis",
                metric="formatting_violations",
                value=lint_res.formatting_violations_count,
                interpretation=(
                    f"Real formatting check: {lint_res.formatting_violations_count} formatting violation(s) detected."
                    if lint_res.tool_real and lint_res.formatter_config_present
                    else ("Formatter configuration present." if lint_res.formatter_config_present else "No explicit formatter configuration found.")
                )
            ))
        else:
            evidence.append(EvidenceItem(
                source="linter_analysis",
                metric="lint_errors",
                value="unmeasurable",
                interpretation="Not measurable with the available submission."
            ))

        # ----------------------------------------------------------------------
        # 2. Type Safety & Strictness
        # ----------------------------------------------------------------------
        type_res = analyze_type_safety(
            root_path=artifact.root_path,
            file_tree=artifact.file_tree,
            detected_languages=artifact.detected_languages,
            config_files=artifact.config_files
        )

        type_pts = 0.0
        if type_res.measurable:
            measurable_dimensions += 1
            if type_res.strict_mode:
                type_pts = max(0.0, 3.5 - (type_res.type_errors_count * 0.5))
                strengths.append(f"Strict static typing system active ({type_res.type_system}).")
            else:
                type_pts = max(0.0, min(3.5, 1.5 + (1.5 * type_res.type_coverage_ratio) - (type_res.type_errors_count * 0.5)))
                if type_res.type_coverage_ratio < 0.5:
                    weaknesses.append(f"Weak or dynamic type safety ({type_res.type_system}).")
                    recommendations.append("Enable strict type checking (e.g. TypeScript strict: true or Python type hints).")

            evidence.append(EvidenceItem(
                source="type_checker",
                metric="type_errors",
                value=type_res.type_errors_count,
                interpretation=f"Type system: {type_res.type_system}. Strict mode: {type_res.strict_mode}.",
                raw_data=type_res.details
            ))
        else:
            evidence.append(EvidenceItem(
                source="type_checker",
                metric="type_errors",
                value="unmeasurable",
                interpretation="Not measurable with the available submission."
            ))

        # ----------------------------------------------------------------------
        # 3. Package & Dependency Hygiene
        # ----------------------------------------------------------------------
        pkg_res = analyze_package_metadata(
            root_path=artifact.root_path,
            package_managers=artifact.package_managers
        )

        pkg_pts = 0.0
        if pkg_res.measurable:
            measurable_dimensions += 1
            base = 2.0 if pkg_res.has_lockfile else 1.0
            if pkg_res.is_valid:
                base += 1.0
            penalties = 0.3 * len(pkg_res.metadata_issues)
            pkg_pts = max(0.0, min(3.0, base - penalties))

            if pkg_res.has_lockfile:
                strengths.append("Deterministic package lockfile committed for reproducible builds.")
            else:
                weaknesses.append("Missing package lockfile (e.g. pnpm-lock.yaml or poetry.lock).")
                recommendations.append("Commit a lockfile to guarantee reproducible build environments.")

            for issue in pkg_res.metadata_issues:
                weaknesses.append(f"Package metadata warning: {issue}")

            evidence.append(EvidenceItem(
                source="package_manifest",
                metric="dependency_count",
                value=pkg_res.dependency_count + pkg_res.dev_dependency_count,
                interpretation=f"Declared {pkg_res.dependency_count} runtime and {pkg_res.dev_dependency_count} dev dependencies.",
                raw_data=pkg_res.details
            ))
        else:
            evidence.append(EvidenceItem(
                source="package_manifest",
                metric="dependency_count",
                value="unmeasurable",
                interpretation="Not measurable with the available submission."
            ))

        # ----------------------------------------------------------------------
        # 4. File Structure & Dead Code
        # ----------------------------------------------------------------------
        struct_res = analyze_file_structure(
            root_path=artifact.root_path,
            file_tree=artifact.file_tree
        )

        struct_pts = 0.0
        if struct_res.measurable:
            measurable_dimensions += 1
            base = 3.0 if struct_res.source_file_count > 0 else 0.5
            penalties = (0.5 * len(struct_res.suspicious_issues)) + (0.2 * min(len(struct_res.dead_code_candidates), 5))
            struct_pts = max(0.0, min(3.0, base - penalties))

            if not struct_res.suspicious_issues:
                strengths.append("Clean project structure with no committed binaries or dependency artifacts.")
            else:
                for s_issue in struct_res.suspicious_issues:
                    weaknesses.append(s_issue)
                recommendations.append("Remove committed binaries or dependency artifacts and update .gitignore.")

            if struct_res.dead_code_candidates:
                weaknesses.append(f"Detected {len(struct_res.dead_code_candidates)} unreferenced source file(s) (possible dead code).")
                recommendations.append(f"Prune unused source files: {', '.join(struct_res.dead_code_candidates[:3])}")

            evidence.append(EvidenceItem(
                source="file_structure",
                metric="source_file_count",
                value=struct_res.source_file_count,
                interpretation=f"Tracked {struct_res.source_file_count} primary source code files."
            ))
            evidence.append(EvidenceItem(
                source="file_structure",
                metric="suspicious_project_structure_issues",
                value=len(struct_res.suspicious_issues),
                interpretation=f"Identified {len(struct_res.suspicious_issues)} suspicious file structure issue(s).",
                raw_data={"issues": struct_res.suspicious_issues}
            ))
            evidence.append(EvidenceItem(
                source="dead_code_analysis",
                metric="dead_code_indicators",
                value=len(struct_res.dead_code_candidates),
                interpretation=f"Flagged {len(struct_res.dead_code_candidates)} unreferenced source files.",
                raw_data={"candidates": struct_res.dead_code_candidates}
            ))
        else:
            evidence.append(EvidenceItem(
                source="file_structure",
                metric="suspicious_project_structure_issues",
                value="unmeasurable",
                interpretation="Not measurable with the available submission."
            ))

        # ----------------------------------------------------------------------
        # 5. Testing Discovery & Hygiene
        # ----------------------------------------------------------------------
        test_res = analyze_tests(
            root_path=artifact.root_path,
            test_files=artifact.test_files,
            detected_languages=artifact.detected_languages,
            detected_frameworks=artifact.detected_frameworks
        )

        test_pts = 0.0
        if test_res.measurable:
            measurable_dimensions += 1
            if test_res.test_count > 0:
                test_pts = max(0.0, min(1.5, 1.5 - (test_res.test_failures * 0.5)))
                strengths.append(f"Automated test suite detected ({test_res.test_count} test cases in {test_res.framework or 'framework'}).")
            else:
                weaknesses.append("No automated test cases discovered in repository.")
                recommendations.append("Implement automated unit and integration tests.")

            evidence.append(EvidenceItem(
                source="test_discovery",
                metric="test_count",
                value=test_res.test_count,
                interpretation=f"Discovered {test_res.test_count} test cases across {test_res.test_files_count} test files.",
                raw_data=test_res.details
            ))
            evidence.append(EvidenceItem(
                source="test_discovery",
                metric="test_failures",
                value=test_res.test_failures,
                interpretation=f"Identified {test_res.test_failures} test file syntax/collection failures."
            ))
        else:
            evidence.append(EvidenceItem(
                source="test_discovery",
                metric="test_count",
                value="unmeasurable",
                interpretation="Not measurable with the available submission."
            ))

        # ----------------------------------------------------------------------
        # Total Score & Confidence Calculation
        # ----------------------------------------------------------------------
        total_score = round(min(self.max_score, max(0.0, lint_pts + type_pts + pkg_pts + struct_pts + test_pts)), 2)
        confidence = round(measurable_dimensions / float(total_dimensions), 2)

        summary = (
            f"Deterministic code quality scored {total_score}/{self.max_score} "
            f"(Static Analysis: {lint_pts:.1f}/4.0, Types: {type_pts:.1f}/3.5, "
            f"Packages: {pkg_pts:.1f}/3.0, Structure: {struct_pts:.1f}/3.0, Tests: {test_pts:.1f}/1.5)."
        )

        return EvaluationResult(
            criterion=self.criterion,
            score=total_score,
            maxScore=self.max_score,
            confidence=confidence,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            evidence=evidence
        )
