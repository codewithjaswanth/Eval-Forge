import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..models import ProjectArtifact

class ContextPacker:
    """
    Extracts, summarizes, and packages repository artifacts into structured context
    for qualitative LLM evaluation.
    """

    @staticmethod
    def pack_context(artifact: ProjectArtifact) -> Dict[str, Any]:
        """Extracts README, description, source structure, documentation, and detected purpose."""
        root = artifact.root_path

        # 1. Project Description
        description = artifact.description or "No submission description provided."

        # 2. README Content
        readme_snippet = artifact.readme_content or "No README file detected in repository."
        if len(readme_snippet) > 4000:
            readme_snippet = readme_snippet[:4000] + "\n\n... [README truncated for length] ..."

        # 3. Documentation Files
        docs_content: List[Dict[str, str]] = []
        doc_candidates = [
            f for f in artifact.file_tree
            if f.lower().startswith("docs/") or f.lower() in [
                "architecture.md", "contributing.md", "api.md", "design.md", "spec.md"
            ]
        ][:5]

        for doc_rel in doc_candidates:
            doc_path = root / doc_rel
            if doc_path.is_file():
                try:
                    txt = doc_path.read_text(encoding="utf-8", errors="ignore")[:1500]
                    docs_content.append({"path": doc_rel, "snippet": txt})
                except Exception:
                    pass

        # 4. Source Directory Structure
        dirs_summary = {}
        for f in artifact.file_tree[:200]:
            parts = f.replace("\\", "/").split("/")
            if len(parts) > 1:
                top_dir = parts[0]
                dirs_summary[top_dir] = dirs_summary.get(top_dir, 0) + 1
            else:
                dirs_summary["(root)"] = dirs_summary.get("(root)", 0) + 1

        formatted_structure = "\n".join([f"  - {d}/: {cnt} file(s)" for d, cnt in sorted(dirs_summary.items())])

        # 5. Detected Application Purpose
        purpose_signals = []
        if artifact.detected_frameworks:
            purpose_signals.append(f"Frameworks: {', '.join(artifact.detected_frameworks)}")
        if artifact.detected_languages:
            purpose_signals.append(f"Languages: {', '.join(artifact.detected_languages[:3])}")
        if artifact.has_frontend and artifact.has_backend:
            purpose_signals.append("Architecture: Decoupled Full-Stack (Client + Server)")
        elif artifact.has_frontend:
            purpose_signals.append("Architecture: Client / Presentation focused")
        elif artifact.has_backend:
            purpose_signals.append("Architecture: Backend API / CLI / Service focused")

        if artifact.live_url:
            purpose_signals.append(f"Live Deployment: {artifact.live_url}")

        detected_purpose = "; ".join(purpose_signals) if purpose_signals else "General software repository"

        return {
            "repository_url": artifact.repository_url,
            "description": description,
            "readme": readme_snippet,
            "documentation": docs_content,
            "source_structure": formatted_structure,
            "detected_purpose": detected_purpose,
            "file_tree_sample": artifact.file_tree[:80]
        }

    @staticmethod
    def format_problem_prompt(context: Dict[str, Any]) -> str:
        """Format prompt for Problem statement evaluation."""
        docs_str = "\n".join([f"--- Doc: {d['path']} ---\n{d['snippet']}" for d in context["documentation"]]) or "None"
        
        return f"""
EVALUATION TARGET:
Repository: {context['repository_url']}
Detected Purpose: {context['detected_purpose']}

USER-PROVIDED PROJECT DESCRIPTION:
{context['description']}

README SNIPPET:
{context['readme']}

DOCUMENTATION FILES:
{docs_str}

SOURCE CODE REPOSITORY STRUCTURE:
{context['source_structure']}

TASK:
Evaluate the problem formulation of this project according to the required schema.
Evaluate each dimension (0.0 to 1.0) with detailed reasoning and exact evidence citations.
Do not invent features or requirements not present in the evidence.
"""

    @staticmethod
    def format_solution_prompt(context: Dict[str, Any], problem_context: Optional[Dict[str, Any]] = None) -> str:
        """Format prompt for Solution quality evaluation."""
        docs_str = "\n".join([f"--- Doc: {d['path']} ---\n{d['snippet']}" for d in context["documentation"]]) or "None"
        files_str = "\n".join([f"  - {f}" for f in context["file_tree_sample"][:60]])

        prob_summary = problem_context.get("summary", "Problem context unavailable.") if problem_context else "Problem context unavailable."
        prob_score = problem_context.get("score", "N/A") if problem_context else "N/A"

        return f"""
EVALUATION TARGET:
Repository: {context['repository_url']}
Detected Purpose: {context['detected_purpose']}

PROBLEM CONTEXT (From Prior Problem Evaluation):
Problem Score: {prob_score}/10.0
Problem Summary: {prob_summary}

USER-PROVIDED PROJECT DESCRIPTION:
{context['description']}

README SNIPPET:
{context['readme']}

DOCUMENTATION:
{docs_str}

SOURCE REPOSITORY STRUCTURE:
{context['source_structure']}

SAMPLE REPOSITORY FILES:
{files_str}

TASK:
Evaluate the technical solution and architecture of this project according to the required schema.
Evaluate each dimension (0.0 to 1.0) with detailed technical reasoning and exact evidence citations.
Do not invent features, architecture layers, or capabilities not present in the evidence.
"""
