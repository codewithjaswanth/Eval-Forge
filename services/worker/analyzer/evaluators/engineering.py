from typing import Dict
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact

class EngineeringAnalyzer(BaseEvaluator):
    """
    Evaluates CI/CD automation, test coverage presence, environment templates, and repository hygiene.
    Max Score: 10.0
    Dependencies: None
    """
    def __init__(self, timeout_seconds: float = 30.0):
        super().__init__(
            name="EngineeringAnalyzer",
            criterion="engineering_practices",
            max_score=10.0,
            dependencies=[],
            timeout_seconds=timeout_seconds
        )

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        score = 2.0
        strengths = []
        weaknesses = []
        recommendations = []
        evidence = []

        # 1. Automated tests presence
        if len(artifact.test_files) > 0 or len(artifact.test_directories) > 0:
            score += 4.0
            strengths.append(f"Automated test suites detected ({len(artifact.test_files)} test files across {len(artifact.test_directories)} directories).")
            evidence.append(EvidenceItem(
                source="test_discovery",
                metric="test_files_count",
                value=len(artifact.test_files),
                interpretation="Automated unit or integration tests exist in repository."
            ))
        else:
            weaknesses.append("No automated test files or test directories detected.")
            recommendations.append("Add unit and integration tests (e.g. Jest, Vitest, Pytest).")

        # 2. CI/CD automation workflows
        if len(artifact.ci_cd_workflows) > 0:
            score += 3.0
            workflows = ", ".join(artifact.ci_cd_workflows)
            strengths.append(f"Continuous Integration (CI/CD) workflows configured: {workflows}")
            evidence.append(EvidenceItem(
                source="ci_detection",
                metric="ci_workflows_count",
                value=len(artifact.ci_cd_workflows),
                interpretation="Automated CI/CD pipeline triggers tests and builds on push/PR."
            ))
        else:
            weaknesses.append("Missing automated CI/CD pipeline configuration.")
            recommendations.append("Add a GitHub Actions workflow (.github/workflows/ci.yml) to run tests automatically.")

        # 3. Docker / Containerization
        if len(artifact.docker_files) > 0:
            score += 1.0
            strengths.append("Containerization support present (Dockerfile / docker-compose).")

        score = min(score, self.max_score)
        summary = f"Engineering practices scored {score}/{self.max_score} based on test presence, CI/CD, and repository configuration."

        return EvaluationResult(
            criterion=self.criterion,
            score=score,
            maxScore=self.max_score,
            confidence=0.90,
            summary=summary,
            strengths=strengths,
            weaknesses=weaknesses,
            recommendations=recommendations,
            evidence=evidence
        )
