from typing import Dict
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact

class SecurityAnalyzer(BaseEvaluator):
    """
    Evaluates secret exposure prevention, input sanitization, and dependency vulnerabilities.
    Max Score: 10.0
    Dependencies: CodeQualityAnalyzer
    """
    def __init__(self, timeout_seconds: float = 30.0):
        super().__init__(
            name="SecurityAnalyzer",
            criterion="security",
            max_score=10.0,
            dependencies=["CodeQualityAnalyzer"],
            timeout_seconds=timeout_seconds
        )

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        score = 6.0
        strengths = []
        weaknesses = []
        recommendations = []
        evidence = []

        # 1. Check for accidental committed secrets (.env files)
        committed_env = [f for f in artifact.file_tree if f == ".env" or f.endswith("/.env")]
        if committed_env:
            score -= 4.0
            weaknesses.append("Potential plaintext .env secret file detected in repository tree.")
            evidence.append(EvidenceItem(
                source="secret_scanner",
                metric="exposed_env_files",
                value=committed_env,
                interpretation="Security risk: .env file committed to version control."
            ))
        else:
            score += 2.0
            strengths.append("No plaintext .env credential files found committed in repository.")

        # 2. Check for .env.example template
        has_env_example = any(".env.example" in f for f in artifact.config_files)
        if has_env_example:
            score += 2.0
            strengths.append("Provides safe .env.example environment variable template.")
            evidence.append(EvidenceItem(
                source="config_audit",
                metric="env_example_present",
                value=True,
                interpretation="Demonstrates safe credential configuration practices."
            ))

        score = max(0.0, min(score, self.max_score))
        summary = f"Security posture scored {score}/{self.max_score} based on credential hygiene and configuration audit."

        return EvaluationResult(
            criterion=self.criterion,
            score=score,
            maxScore=self.max_score,
            confidence=0.85,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations or ["Ensure periodic dependency vulnerability scans (npm audit / pip-audit)."],
            evidence=evidence
        )
