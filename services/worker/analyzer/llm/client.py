import os
import json
import logging
from typing import Dict, Any, Optional, List, Type, TypeVar
from pydantic import BaseModel, ValidationError

from ..rubrics.models import (
    ProblemRubricEvaluation,
    SolutionRubricEvaluation,
    RubricDimensionScore
)
from .context_packer import ContextPacker

logger = logging.getLogger("evalforge.llm.client")

T = TypeVar("T", bound=BaseModel)

SYSTEM_INSTRUCTION = """You are an expert, objective software evaluation auditor for EvalForge.
CRITICAL INTEGRITY CONSTRAINTS:
1. You MUST NOT invent, assume, or hallucinate features, components, endpoints, database schemas, or capabilities that are not explicitly evidenced in the repository files, directory tree, or description provided in the context.
2. If an element or requirement is absent or ambiguous, penalize the corresponding dimension score and explicitly cite its absence.
3. Every claim and score MUST cite verifiable evidence (e.g. 'README.md', specific file paths from the repository tree, or exact phrases from the user description).
4. Do not assign arbitrary overall scores. Evaluate each individual rubric dimension strictly between 0.0 (unacceptable/missing) and 1.0 (exemplary).
5. Output ONLY a valid JSON object strictly matching the requested schema.
"""

class LLMClientError(Exception):
    pass

class LLMMalformedResponseError(LLMClientError):
    pass

class BaseLLMClient:
    """Abstract base LLM client interface for structured evaluation."""
    def __init__(self, model_name: str = "mock-llm-v1"):
        self.model_name = model_name

    def evaluate_problem(self, context: Dict[str, Any], max_retries: int = 2) -> ProblemRubricEvaluation:
        raise NotImplementedError

    def evaluate_solution(
        self,
        context: Dict[str, Any],
        problem_context: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> SolutionRubricEvaluation:
        raise NotImplementedError

class MockLLMClient(BaseLLMClient):
    """
    Deterministic mock LLM client for testing and offline runs.
    Inspects project context to produce grounded, schema-validated rubric evaluations.
    """
    def __init__(
        self,
        model_name: str = "mock-llm-v1",
        custom_problem_response: Optional[Dict[str, Any]] = None,
        custom_solution_response: Optional[Dict[str, Any]] = None,
        fail_count: int = 0
    ):
        super().__init__(model_name=model_name)
        self.custom_problem_response = custom_problem_response
        self.custom_solution_response = custom_solution_response
        self.fail_count = fail_count
        self.attempts = 0

    def evaluate_problem(self, context: Dict[str, Any], max_retries: int = 2) -> ProblemRubricEvaluation:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise LLMMalformedResponseError(f"Simulated malformed LLM response on attempt {self.attempts}")

        if self.custom_problem_response:
            try:
                return ProblemRubricEvaluation.model_validate(self.custom_problem_response)
            except ValidationError as ve:
                raise LLMMalformedResponseError(f"Custom problem response failed schema validation: {ve}")

        # Deterministic generation from context
        desc = context.get("description", "")
        has_clear_desc = len(desc.strip()) > 30 and "No submission description" not in desc
        readme = context.get("readme", "")
        has_readme = len(readme.strip()) > 40 and "No README" not in readme

        clarity_score = 0.90 if has_clear_desc else (0.65 if has_readme else 0.30)
        spec_score = 0.85 if has_readme and ("getting started" in readme.lower() or "architecture" in readme.lower()) else 0.50
        importance_score = 0.80 if has_clear_desc or has_readme else 0.40
        users_score = 0.85 if "user" in desc.lower() or "for " in desc.lower() or "developer" in readme.lower() else 0.50
        constraints_score = 0.75 if "limit" in readme.lower() or "require" in readme.lower() or "prerequisite" in readme.lower() else 0.45
        understanding_score = 0.85 if has_clear_desc and has_readme else 0.50

        citations_list = []
        if has_clear_desc:
            citations_list.append("project description")
        if has_readme:
            citations_list.append("README.md")

        return ProblemRubricEvaluation(
            clarity=RubricDimensionScore(
                score=clarity_score,
                reasoning="Problem statement articulates primary operational requirements and objectives.",
                citations=citations_list
            ),
            specificity=RubricDimensionScore(
                score=spec_score,
                reasoning="Scope and boundaries are defined through configuration and documentation.",
                citations=citations_list
            ),
            importance=RubricDimensionScore(
                score=importance_score,
                reasoning="Addresses concrete software automation and evaluation pain points.",
                citations=citations_list
            ),
            affected_users=RubricDimensionScore(
                score=users_score,
                reasoning="Identifies developer and software engineering personas.",
                citations=citations_list
            ),
            constraints=RubricDimensionScore(
                score=constraints_score,
                reasoning="Notes environment requirements and dependency constraints.",
                citations=citations_list
            ),
            evidence_of_understanding=RubricDimensionScore(
                score=understanding_score,
                reasoning="Demonstrates technical comprehension of root causes rather than superficial symptoms.",
                citations=citations_list
            ),
            detected_problem_summary="Automated evaluation and quality analysis for modern software repositories.",
            strengths=["Clear intent documented in submission metadata", "README guides project setup"],
            weaknesses=[] if has_clear_desc else ["Lacks detailed problem background in submission"],
            recommendations=["Add explicit user personas and operating constraints to README.md"]
        )

    def evaluate_solution(
        self,
        context: Dict[str, Any],
        problem_context: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> SolutionRubricEvaluation:
        self.attempts += 1
        if self.attempts <= self.fail_count:
            raise LLMMalformedResponseError(f"Simulated malformed LLM response on attempt {self.attempts}")

        if self.custom_solution_response:
            try:
                return SolutionRubricEvaluation.model_validate(self.custom_solution_response)
            except ValidationError as ve:
                raise LLMMalformedResponseError(f"Custom solution response failed schema validation: {ve}")

        files = context.get("file_tree_sample", [])
        purpose = context.get("detected_purpose", "")

        has_frontend = "Client" in purpose or "Presentation" in purpose or "Full-Stack" in purpose
        has_backend = "Backend" in purpose or "Full-Stack" in purpose or any("server" in f or "api" in f for f in files)

        arch_score = 0.90 if has_frontend and has_backend else 0.75
        correct_score = 0.85
        relevance_score = 0.90
        feasibility_score = 0.85
        completeness_score = 0.80 if len(files) >= 5 else 0.50
        tech_score = 0.85 if "Frameworks:" in purpose else 0.60
        trade_offs_score = 0.75

        citations = [f for f in files[:4]]
        if "package.json" in files:
            citations.append("package.json")

        return SolutionRubricEvaluation(
            correctness=RubricDimensionScore(
                score=correct_score,
                reasoning="Technical implementation matches the declared problem scope and tech stack.",
                citations=citations
            ),
            relevance_to_problem=RubricDimensionScore(
                score=relevance_score,
                reasoning="Components directly implement the required workflows without extraneous scaffolding.",
                citations=citations
            ),
            architecture=RubricDimensionScore(
                score=arch_score,
                reasoning="Clean separation between application presentation and business logic layers.",
                citations=citations
            ),
            feasibility=RubricDimensionScore(
                score=feasibility_score,
                reasoning="Employs standard runtime dependencies and containerizable configuration.",
                citations=citations
            ),
            completeness=RubricDimensionScore(
                score=completeness_score,
                reasoning="Contains necessary source modules, configuration files, and build manifests.",
                citations=citations
            ),
            technical_reasoning=RubricDimensionScore(
                score=tech_score,
                reasoning="Technology choices reflect cohesive modern framework practices.",
                citations=citations
            ),
            trade_offs=RubricDimensionScore(
                score=trade_offs_score,
                reasoning="Balances development velocity with static type safety and modular design.",
                citations=citations
            ),
            detected_solution_summary="Modular multi-tier application architecture utilizing cohesive frameworks.",
            strengths=["Well-defined directory boundaries", "Modern build and dependency management"],
            weaknesses=[] if len(files) >= 5 else ["Minimal file tree may indicate incomplete implementation"],
            recommendations=["Document architecture data flows and database schema migrations"]
        )

class GeminiLLMClient(BaseLLMClient):
    """
    Live Google Gemini LLM client enforcing structured JSON output.
    """
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        super().__init__(model_name=model_name)
        self.api_key = api_key

    def _call_gemini_structured(self, prompt: str, schema_class: Type[T], max_retries: int) -> T:
        import urllib.request
        import urllib.error

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent?key={self.api_key}"

        schema_json = json.dumps(schema_class.model_json_schema())
        full_prompt = f"{prompt}\n\nYou MUST format your output strictly as a JSON object adhering to this JSON Schema:\n{schema_json}"

        payload = {
            "contents": [{"parts": [{"text": full_prompt}]}],
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "generationConfig": {
                "temperature": 0.0,
                "responseMimeType": "application/json"
            }
        }

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_body = json.loads(response.read().decode("utf-8"))
                    text_content = res_body["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = schema_class.model_validate_json(text_content)
                    return parsed
            except Exception as e:
                last_error = e
                logger.warning(f"[GeminiLLMClient] Attempt {attempt + 1} failed: {e}. Retrying...")

        raise LLMMalformedResponseError(f"Gemini structured generation failed after {max_retries + 1} attempts: {last_error}")

    def evaluate_problem(self, context: Dict[str, Any], max_retries: int = 2) -> ProblemRubricEvaluation:
        prompt = ContextPacker.format_problem_prompt(context)
        return self._call_gemini_structured(prompt, ProblemRubricEvaluation, max_retries=max_retries)

    def evaluate_solution(
        self,
        context: Dict[str, Any],
        problem_context: Optional[Dict[str, Any]] = None,
        max_retries: int = 2
    ) -> SolutionRubricEvaluation:
        prompt = ContextPacker.format_solution_prompt(context, problem_context)
        return self._call_gemini_structured(prompt, SolutionRubricEvaluation, max_retries=max_retries)

def get_llm_client(force_mock: bool = False) -> BaseLLMClient:
    """Factory creating live GeminiLLMClient if API key present, else deterministic MockLLMClient."""
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key and not force_mock:
        return GeminiLLMClient(api_key=api_key)
    return MockLLMClient()
