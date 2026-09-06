import unittest
import sys
from pathlib import Path
from typing import Dict, Any

# Add services/worker to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from analyzer.models import ProjectArtifact
from analyzer.evaluators.problem_analyzer import ProblemAnalyzer, RUBRIC_VERSION, EVALUATOR_VERSION
from analyzer.evaluators.solution_analyzer import SolutionAnalyzer
from analyzer.evaluators.base import EvaluationResult
from analyzer.llm import (
    MockLLMClient,
    ContextPacker,
    LLMMalformedResponseError
)
from analyzer.rubrics import (
    ProblemRubricEvaluation,
    SolutionRubricEvaluation,
    RubricDimensionScore,
    calculate_problem_score,
    calculate_solution_score
)

def make_sample_artifact():
    return ProjectArtifact(
        root_path=Path("/tmp/sample_repo"),
        source_type="test_fixture",
        repository_url="https://github.com/test-org/eval-forge",
        commit_sha="112233445566",
        branch="main",
        live_url="https://evalforge.dev",
        description="An AI-powered software project evaluation platform for hackathons and talent assessment.",
        detected_languages=["TypeScript", "Python"],
        detected_frameworks=["Next.js", "React", "FastAPI"],
        package_managers=["pnpm", "pip"],
        has_frontend=True,
        has_backend=True,
        has_readme=True,
        readme_content="# EvalForge\n\n## Overview\nEvalForge automates software evaluation using deterministic tools and LLMs.\n\n## Constraints\nRequires Node 18+ and Python 3.12+.",
        test_files=["tests/test_app.py"],
        file_tree=[
            "package.json", "tsconfig.json", "src/app/page.tsx", "src/server.ts",
            "tests/test_app.py", "README.md", "docs/architecture.md"
        ]
    )

class TestProblemAndSolutionAnalyzers(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.artifact = make_sample_artifact()

    # --------------------------------------------------------------------------
    # 1. ContextPacker Unit Tests
    # --------------------------------------------------------------------------
    def test_context_packer_extraction(self):
        ctx = ContextPacker.pack_context(self.artifact)

        self.assertIn("EvalForge automates software evaluation", ctx["readme"])
        self.assertEqual(ctx["description"], self.artifact.description)
        self.assertIn("Next.js", ctx["detected_purpose"])
        self.assertIn("Full-Stack", ctx["detected_purpose"])
        self.assertGreater(len(ctx["source_structure"]), 0)

        prob_prompt = ContextPacker.format_problem_prompt(ctx)
        self.assertIn("EVALUATION TARGET:", prob_prompt)
        self.assertIn("USER-PROVIDED PROJECT DESCRIPTION:", prob_prompt)

        sol_prompt = ContextPacker.format_solution_prompt(ctx, {"score": 9.0, "summary": "Clear problem"})
        self.assertIn("PROBLEM CONTEXT", sol_prompt)
        self.assertIn("9.0/10.0", sol_prompt)

    # --------------------------------------------------------------------------
    # 2. ProblemAnalyzer Execution & Evidence Verification
    # --------------------------------------------------------------------------
    async def test_problem_analyzer_execution(self):
        llm_client = MockLLMClient(model_name="test-mock-gemini")
        analyzer = ProblemAnalyzer(llm_client=llm_client)

        result = await analyzer.run_safe(artifact=self.artifact, context={})

        self.assertTrue(analyzer.validate(result))
        self.assertEqual(result.criterion, "problem_statement")
        self.assertEqual(result.maxScore, 10.0)
        self.assertGreater(result.score, 0.0)
        self.assertLessEqual(result.score, 10.0)
        self.assertGreater(result.confidence, 0.7)

        # Check all 6 rubric dimensions exist in evidence
        evidence_by_metric = {e.metric: e for e in result.evidence}
        expected_dims = [
            "dimension_clarity", "dimension_specificity", "dimension_importance",
            "dimension_affected_users", "dimension_constraints", "dimension_evidence_of_understanding"
        ]
        for dim in expected_dims:
            self.assertIn(dim, evidence_by_metric)
            e = evidence_by_metric[dim]
            self.assertGreaterEqual(e.value, 0.0)
            self.assertLessEqual(e.value, 1.0)
            self.assertIsNotNone(e.interpretation)

        # Check metadata evidence
        self.assertIn("evaluation_metadata", evidence_by_metric)
        meta_ev = evidence_by_metric["evaluation_metadata"]
        self.assertEqual(meta_ev.raw_data["model_name"], "test-mock-gemini")
        self.assertEqual(meta_ev.raw_data["rubric_version"], RUBRIC_VERSION)
        self.assertEqual(meta_ev.raw_data["evaluator_version"], EVALUATOR_VERSION)

    # --------------------------------------------------------------------------
    # 3. SolutionAnalyzer Execution & Dependency Handling
    # --------------------------------------------------------------------------
    async def test_solution_analyzer_execution(self):
        problem_res = EvaluationResult(
            criterion="problem_statement",
            score=8.5,
            maxScore=10.0,
            confidence=0.9,
            summary="Strong problem definition with clear constraints."
        )

        llm_client = MockLLMClient(model_name="test-mock-gemini")
        analyzer = SolutionAnalyzer(llm_client=llm_client)

        result = await analyzer.run_safe(
            artifact=self.artifact,
            context={"ProblemAnalyzer": problem_res}
        )

        self.assertTrue(analyzer.validate(result))
        self.assertEqual(result.criterion, "solution_quality")
        self.assertEqual(result.maxScore, 15.0)
        self.assertGreater(result.score, 0.0)
        self.assertLessEqual(result.score, 15.0)

        # Check all 7 rubric dimensions exist in evidence
        evidence_by_metric = {e.metric: e for e in result.evidence}
        expected_dims = [
            "dimension_correctness", "dimension_relevance_to_problem", "dimension_architecture",
            "dimension_feasibility", "dimension_completeness", "dimension_technical_reasoning",
            "dimension_trade_offs"
        ]
        for dim in expected_dims:
            self.assertIn(dim, evidence_by_metric)
            e = evidence_by_metric[dim]
            self.assertGreaterEqual(e.value, 0.0)
            self.assertLessEqual(e.value, 1.0)

        # Verify metadata
        self.assertIn("evaluation_metadata", evidence_by_metric)
        self.assertEqual(evidence_by_metric["evaluation_metadata"].raw_data["rubric_version"], "1.0.0")

    # --------------------------------------------------------------------------
    # 4. Deterministic Dimension Score Aggregation
    # --------------------------------------------------------------------------
    def test_deterministic_scoring_functions(self):
        # Perfect Problem Score: all dimensions = 1.0
        perfect_problem = ProblemRubricEvaluation(
            clarity=RubricDimensionScore(score=1.0, reasoning="Crystal clear"),
            specificity=RubricDimensionScore(score=1.0, reasoning="Very specific"),
            importance=RubricDimensionScore(score=1.0, reasoning="Critical challenge"),
            affected_users=RubricDimensionScore(score=1.0, reasoning="Defined users"),
            constraints=RubricDimensionScore(score=1.0, reasoning="Clear constraints"),
            evidence_of_understanding=RubricDimensionScore(score=1.0, reasoning="Deep understanding"),
            detected_problem_summary="Exemplary problem statement"
        )
        score_10, breakdown_10 = calculate_problem_score(perfect_problem)
        self.assertEqual(score_10, 10.0)
        self.assertEqual(breakdown_10["clarity"], 2.0)
        self.assertEqual(breakdown_10["importance"], 1.5)

        # Half Problem Score: all dimensions = 0.5
        half_problem = ProblemRubricEvaluation(
            clarity=RubricDimensionScore(score=0.5, reasoning="Acceptable clarity"),
            specificity=RubricDimensionScore(score=0.5, reasoning="Vague scope"),
            importance=RubricDimensionScore(score=0.5, reasoning="Moderate value"),
            affected_users=RubricDimensionScore(score=0.5, reasoning="Broad audience"),
            constraints=RubricDimensionScore(score=0.5, reasoning="Partial constraints"),
            evidence_of_understanding=RubricDimensionScore(score=0.5, reasoning="Basic symptoms only"),
            detected_problem_summary="Moderate problem statement"
        )
        score_5, _ = calculate_problem_score(half_problem)
        self.assertEqual(score_5, 5.0)

        # Perfect Solution Score: all dimensions = 1.0 -> 15.0
        perfect_solution = SolutionRubricEvaluation(
            correctness=RubricDimensionScore(score=1.0, reasoning="Flawless logic"),
            relevance_to_problem=RubricDimensionScore(score=1.0, reasoning="100% relevant"),
            architecture=RubricDimensionScore(score=1.0, reasoning="Clean architecture"),
            feasibility=RubricDimensionScore(score=1.0, reasoning="Highly feasible"),
            completeness=RubricDimensionScore(score=1.0, reasoning="Complete system"),
            technical_reasoning=RubricDimensionScore(score=1.0, reasoning="Justified choices"),
            trade_offs=RubricDimensionScore(score=1.0, reasoning="Handled trade-offs"),
            detected_solution_summary="Exemplary solution architecture"
        )
        score_15, breakdown_15 = calculate_solution_score(perfect_solution)
        self.assertEqual(score_15, 15.0)
        self.assertEqual(breakdown_15["correctness"], 2.5)
        self.assertEqual(breakdown_15["feasibility"], 2.0)
        self.assertEqual(breakdown_15["trade_offs"], 1.5)

    # --------------------------------------------------------------------------
    # 5. Malformed Response Rejection & Error Handling
    # --------------------------------------------------------------------------
    async def test_malformed_response_rejection(self):
        # Client that fails permanently with malformed response
        malformed_client = MockLLMClient(fail_count=5)
        analyzer = ProblemAnalyzer(llm_client=malformed_client)

        result = await analyzer.run_safe(artifact=self.artifact, context={})

        self.assertTrue(result.is_error)
        self.assertEqual(result.score, 0.0)
        self.assertIn("Malformed LLM response rejected", result.summary)
        self.assertIn("failed strict schema validation", " ".join(result.weaknesses))

    # --------------------------------------------------------------------------
    # 6. Anti-Fabrication & Citation Verification
    # --------------------------------------------------------------------------
    async def test_citations_verified_against_file_tree(self):
        # Mock response citing real files and one fabricated file
        custom_problem = {
            "clarity": {"score": 0.9, "reasoning": "Clear description", "citations": ["README.md", "fake_nonexistent_file.py"]},
            "specificity": {"score": 0.8, "reasoning": "Well specified", "citations": ["src/server.ts"]},
            "importance": {"score": 0.8, "reasoning": "Significant", "citations": ["project description"]},
            "affected_users": {"score": 0.8, "reasoning": "Developers", "citations": []},
            "constraints": {"score": 0.8, "reasoning": "Node/Python", "citations": ["README.md"]},
            "evidence_of_understanding": {"score": 0.8, "reasoning": "Understands issue", "citations": []},
            "detected_problem_summary": "Problem statement for test",
            "strengths": ["Clear docs"],
            "weaknesses": [],
            "recommendations": []
        }

        client = MockLLMClient(custom_problem_response=custom_problem)
        analyzer = ProblemAnalyzer(llm_client=client)
        result = await analyzer.run_safe(artifact=self.artifact, context={})

        # Find clarity dimension evidence
        clarity_ev = next(e for e in result.evidence if e.metric == "dimension_clarity")
        citations = clarity_ev.raw_data["citations"]

        # README.md should be verified=True, fake_nonexistent_file.py should be verified=False
        readme_cit = next(c for c in citations if "README.md" in c["citation"])
        self.assertTrue(readme_cit["verified"])

        fake_cit = next(c for c in citations if "fake_nonexistent_file.py" in c["citation"])
        self.assertFalse(fake_cit["verified"])
        self.assertEqual(fake_cit["note"], "Unverified reference")

if __name__ == "__main__":
    unittest.main()
