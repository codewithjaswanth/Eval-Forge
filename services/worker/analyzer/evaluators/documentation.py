from typing import Dict
from .base import BaseEvaluator, EvaluationResult, EvidenceItem
from ..models import ProjectArtifact

class DocumentationAnalyzer(BaseEvaluator):
    """
    Evaluates README quality, local installation instructions, architecture diagrams, and API docs.
    Max Score: 5.0
    Dependencies: None
    """
    def __init__(self, timeout_seconds: float = 30.0):
        super().__init__(
            name="DocumentationAnalyzer",
            criterion="documentation",
            max_score=5.0,
            dependencies=[],
            timeout_seconds=timeout_seconds
        )

    async def execute(
        self,
        artifact: ProjectArtifact,
        context: Dict[str, EvaluationResult]
    ) -> EvaluationResult:
        score = 1.0
        strengths = []
        weaknesses = []
        recommendations = []
        evidence = []

        if artifact.has_readme and artifact.readme_content:
            content = artifact.readme_content.lower()
            score += 2.0
            strengths.append("Project includes a readable README documentation file.")
            
            # Check for setup / install guide
            if any(term in content for term in ["install", "getting started", "setup", "quickstart", "run"]):
                score += 1.0
                strengths.append("README includes setup and installation instructions.")
            else:
                weaknesses.append("README lacks explicit setup or installation commands.")
                recommendations.append("Add a 'Getting Started' section with exact setup commands.")

            # Check for architecture or usage
            if any(term in content for term in ["architecture", "usage", "overview", "features", "api"]):
                score += 1.0
                strengths.append("README documents architecture, features, or usage examples.")

            evidence.append(EvidenceItem(
                source="readme_parser",
                metric="readme_length_chars",
                value=len(artifact.readme_content),
                interpretation=f"README contains {len(artifact.readme_content)} characters of documentation."
            ))
        else:
            weaknesses.append("No README found in repository.")
            recommendations.append("Create a comprehensive README.md with project overview and setup steps.")

        score = min(score, self.max_score)
        summary = f"Documentation scored {score}/{self.max_score} based on README completeness and setup instructions."

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
