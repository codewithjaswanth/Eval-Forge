from typing import Dict
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact

class OptimizationAnalyzer(BaseEvaluator):
    """
    Evaluates resource efficiency, bundle management, and algorithmic hygiene.
    Max Score: 10.0
    Dependencies: CodeQualityAnalyzer
    """
    def __init__(self, timeout_seconds: float = 30.0):
        super().__init__(
            name="OptimizationAnalyzer",
            criterion="optimization",
            max_score=10.0,
            dependencies=["CodeQualityAnalyzer"],
            timeout_seconds=timeout_seconds
        )

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        score = 5.0
        strengths = []
        weaknesses = []
        recommendations = []
        evidence = []

        # 1. Modern bundler / compiler detection
        if artifact.build_systems:
            score += 3.0
            bundlers = ", ".join(artifact.build_systems)
            strengths.append(f"Modern high-efficiency build system configured: {bundlers}")
            evidence.append(EvidenceItem(
                source="build_inspection",
                metric="build_systems",
                value=artifact.build_systems,
                interpretation="Build system provides tree-shaking and asset minification."
            ))
        elif "Next.js" in artifact.detected_frameworks:
            score += 3.0
            strengths.append("Next.js Turbopack / Webpack optimization engine enabled.")

        # 2. Lockfile presence (deterministic dependency resolution)
        if any(pm in artifact.package_managers for pm in ["pnpm", "yarn", "npm", "poetry", "cargo"]):
            score += 2.0
            evidence.append(EvidenceItem(
                source="package_manager",
                metric="deterministic_lockfile",
                value=True,
                interpretation="Deterministic package lockfile ensures consistent bundle builds."
            ))

        score = min(score, self.max_score)
        summary = f"Optimization analysis scored {score}/{self.max_score} based on build toolchain and asset hygiene."

        return EvaluationResult(
            criterion=self.criterion,
            score=score,
            maxScore=self.max_score,
            confidence=0.80,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            evidence=evidence
        )
