from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class RubricDimensionScore(BaseModel):
    """Evaluation score and reasoning for an individual rubric dimension."""
    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized dimension score between 0.0 (unacceptable/absent) and 1.0 (exemplary)."
    )
    reasoning: str = Field(
        ...,
        min_length=10,
        description="Detailed technical reasoning grounded strictly in evidence found in the repository or description."
    )
    citations: List[str] = Field(
        default_factory=list,
        description="Exact citations to repository files (e.g. 'README.md', 'src/server.ts'), lines, or description excerpts."
    )

class ProblemRubricEvaluation(BaseModel):
    """
    Explicit multi-dimensional rubric for Problem statement quality.
    Total weight: 10.0 points.
    """
    clarity: RubricDimensionScore = Field(
        ...,
        description="Clarity of problem definition: Is the core pain point articulated without ambiguous buzzwords? (Weight: 2.0)"
    )
    specificity: RubricDimensionScore = Field(
        ...,
        description="Specificity: Is the technical/domain boundary and scope explicitly demarcated? (Weight: 2.0)"
    )
    importance: RubricDimensionScore = Field(
        ...,
        description="Importance & Relevance: Is this a meaningful real-world problem or non-trivial technical challenge? (Weight: 1.5)"
    )
    affected_users: RubricDimensionScore = Field(
        ...,
        description="Target Audience: Are affected users, stakeholders, or operational personas clearly identified? (Weight: 1.5)"
    )
    constraints: RubricDimensionScore = Field(
        ...,
        description="Constraints & Boundaries: Are technical, performance, or operational constraints acknowledged? (Weight: 1.5)"
    )
    evidence_of_understanding: RubricDimensionScore = Field(
        ...,
        description="Depth of Understanding: Does the submission differentiate root causes from superficial symptoms? (Weight: 1.5)"
    )
    detected_problem_summary: str = Field(
        ...,
        min_length=20,
        description="Synthesized summary of the core problem being addressed based exclusively on project evidence."
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Key strengths identified in the problem formulation."
    )
    weaknesses: List[str] = Field(
        default_factory=list,
        description="Gaps or weaknesses identified in the problem formulation."
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Actionable recommendations to improve problem articulation."
    )

class SolutionRubricEvaluation(BaseModel):
    """
    Explicit multi-dimensional rubric for Solution quality.
    Total weight: 15.0 points.
    """
    correctness: RubricDimensionScore = Field(
        ...,
        description="Correctness: Does the technical approach soundly resolve the stated problem? (Weight: 2.5)"
    )
    relevance_to_problem: RubricDimensionScore = Field(
        ...,
        description="Relevance: How directly does the codebase tackle the problem versus extraneous tooling? (Weight: 2.5)"
    )
    architecture: RubricDimensionScore = Field(
        ...,
        description="Architecture & Modularity: Separation of concerns, module boundaries, component cohesion, and data flow. (Weight: 2.5)"
    )
    feasibility: RubricDimensionScore = Field(
        ...,
        description="Feasibility & Robustness: Can this implementation operate reliably in real-world environments? (Weight: 2.0)"
    )
    completeness: RubricDimensionScore = Field(
        ...,
        description="Completeness: Is this an end-to-end working system or merely a stub/placeholder? (Weight: 2.0)"
    )
    technical_reasoning: RubricDimensionScore = Field(
        ...,
        description="Technical Reasoning: Are technology and framework choices justified by problem requirements? (Weight: 2.0)"
    )
    trade_offs: RubricDimensionScore = Field(
        ...,
        description="Trade-off Awareness: Does the solution demonstrate awareness and handling of technical trade-offs? (Weight: 1.5)"
    )
    detected_solution_summary: str = Field(
        ...,
        min_length=20,
        description="Synthesized summary of the technical solution and architecture based exclusively on project evidence."
    )
    strengths: List[str] = Field(
        default_factory=list,
        description="Key architectural and technical strengths of the solution."
    )
    weaknesses: List[str] = Field(
        default_factory=list,
        description="Architectural limitations, missing components, or design flaws."
    )
    recommendations: List[str] = Field(
        default_factory=list,
        description="Actionable engineering recommendations to improve the solution."
    )
