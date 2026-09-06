import os
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone

logger = logging.getLogger("evalforge.db")

class EvaluationDatabase:
    """
    Database interface for EvalForge worker.
    Provides atomic job claiming, status tracking, and metadata persistence.
    Supports Supabase REST/PostgreSQL and in-memory mock store for unit testing.
    """
    def __init__(self, use_mock: bool = False):
        self.use_mock = use_mock or not os.getenv("SUPABASE_URL")
        self._supabase_client = None
        self.mock_runs: Dict[str, Dict[str, Any]] = {}
        self.mock_submissions: Dict[str, Dict[str, Any]] = {}
        self.mock_projects: Dict[str, Dict[str, Any]] = {}
        self.mock_modules: Dict[str, Dict[str, Any]] = {}
        self.mock_scores: Dict[str, Dict[str, Any]] = {}
        self.mock_evidence: List[Dict[str, Any]] = []
        self.mock_reports: Dict[str, Dict[str, Any]] = {}

        if not self.use_mock:
            self._init_supabase_client()

    def _init_supabase_client(self):
        """Initialize persistent Supabase connection with session pooling."""
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if url and key:
                self._supabase_client = create_client(url, key)
                logger.info("Initialized persistent Supabase client connection.")
        except Exception as e:
            logger.warning(f"Failed to pre-initialize Supabase client: {e}")

    def _get_client(self):
        """Return cached Supabase client or initialize on-demand."""
        if self._supabase_client is not None:
            return self._supabase_client
        self._init_supabase_client()
        return self._supabase_client

    def claim_next_run(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """
        Atomically claim the next queued evaluation run.
        Uses PostgreSQL SKIP LOCKED semantics or atomic in-memory queue.
        """
        if self.use_mock:
            for run_id, run in self.mock_runs.items():
                if run["status"] == "queued":
                    run["status"] = "running"
                    run["worker_id"] = worker_id
                    run["started_at"] = datetime.now(timezone.utc).isoformat()
                    logger.info(f"Worker {worker_id} atomically claimed mock run: {run_id}")
                    return run
            return None

        # Real Supabase/PostgreSQL client execution using persistent client
        try:
            client = self._get_client()
            if not client:
                return None
            
            # Execute stored procedure claim_next_evaluation_run
            res = client.rpc("claim_next_evaluation_run", {"p_worker_id": worker_id}).execute()
            if res.data and len(res.data) > 0:
                claimed = res.data[0]
                logger.info(f"Worker {worker_id} claimed run: {claimed['id']}")
                return claimed
            return None
        except Exception as e:
            logger.error(f"Error querying queue from Supabase: {e}")
            return None

    def batch_upsert_modules(self, run_id: str, module_defs: List[Dict[str, Any]]):
        """Batch insert/upsert all module status definitions in one single database call."""
        now_str = datetime.now(timezone.utc).isoformat()
        if self.use_mock:
            for m in module_defs:
                mod_name = m["module_name"]
                mod_id = f"mod_{run_id}_{mod_name}"
                self.mock_modules[mod_id] = {
                    "id": mod_id,
                    "run_id": run_id,
                    "module_name": mod_name,
                    "status": m.get("status", "pending"),
                    "max_score": m.get("max_score", 10.0),
                    "score": m.get("score"),
                    "confidence": m.get("confidence"),
                    "error_information": m.get("error_information"),
                    "started_at": m.get("started_at"),
                    "completed_at": m.get("completed_at"),
                    "created_at": now_str,
                    "updated_at": now_str,
                }
            return

        try:
            client = self._get_client()
            if not client:
                return
            rows = []
            for m in module_defs:
                rows.append({
                    "run_id": run_id,
                    "module_name": m["module_name"],
                    "status": m.get("status", "pending"),
                    "max_score": m.get("max_score", 10.0),
                    "score": m.get("score"),
                    "confidence": m.get("confidence"),
                    "error_information": m.get("error_information"),
                    "started_at": m.get("started_at"),
                    "completed_at": m.get("completed_at"),
                    "updated_at": now_str,
                })
            client.table("evaluation_modules").upsert(rows, on_conflict="run_id,module_name").execute()
        except Exception as e:
            logger.error(f"Error batch upserting modules for run {run_id}: {e}")

    def get_submission_and_project(self, submission_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """Fetch submission record and associated project."""
        if self.use_mock:
            sub = self.mock_submissions.get(submission_id)
            proj = self.mock_projects.get(sub.get("project_id")) if sub else None
            return (sub, proj)

        try:
            client = self._get_client()
            if not client:
                return (None, None)
            sub_res = client.table("submissions").select("*").eq("id", submission_id).single().execute()
            sub = sub_res.data
            if sub:
                proj_res = client.table("projects").select("*").eq("id", sub["project_id"]).single().execute()
                return (sub, proj_res.data)
            return (None, None)
        except Exception as e:
            logger.error(f"Error fetching submission {submission_id}: {e}")
            return (None, None)

    def record_ingestion_success(self, run_id: str, submission_id: str, artifact_dict: Dict[str, Any]):
        """Update submission and run with extracted ProjectArtifact metadata."""
        if self.use_mock:
            if submission_id in self.mock_submissions:
                self.mock_submissions[submission_id]["metadata"] = artifact_dict
                self.mock_submissions[submission_id]["status"] = "processed"
                self.mock_submissions[submission_id]["commit_hash"] = artifact_dict.get("commit_sha")
            if run_id in self.mock_runs:
                self.mock_runs[run_id]["status"] = "running"
                self.mock_runs[run_id]["metadata"] = artifact_dict
            return

        try:
            client = self._get_client()
            if not client:
                return
            client.table("submissions").update({
                "metadata": artifact_dict,
                "status": "processed",
                "commit_hash": artifact_dict.get("commit_sha")
            }).eq("id", submission_id).execute()
        except Exception as e:
            logger.error(f"Error recording ingestion metadata for {submission_id}: {e}")

    def mark_run_completed(self, run_id: str, overall_score: float = 0.0, confidence: float = 1.0):
        """Mark evaluation run as completed."""
        if self.use_mock:
            if run_id in self.mock_runs:
                self.mock_runs[run_id]["status"] = "completed"
                self.mock_runs[run_id]["overall_score"] = overall_score
                self.mock_runs[run_id]["confidence_score"] = confidence
                self.mock_runs[run_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            return

        try:
            client = self._get_client()
            if not client:
                return
            client.table("evaluation_runs").update({
                "status": "completed",
                "overall_score": overall_score,
                "confidence_score": confidence,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", run_id).execute()
        except Exception as e:
            logger.error(f"Error marking run {run_id} completed: {e}")

    def mark_run_failed(self, run_id: str, error_message: str):
        """Mark evaluation run as failed and record error information."""
        if self.use_mock:
            if run_id in self.mock_runs:
                self.mock_runs[run_id]["status"] = "failed"
                self.mock_runs[run_id]["error_information"] = {"error": error_message}
                self.mock_runs[run_id]["completed_at"] = datetime.now(timezone.utc).isoformat()
            return

        try:
            client = self._get_client()
            if not client:
                return
            client.table("evaluation_runs").update({
                "status": "failed",
                "error_information": {"error": error_message},
                "completed_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", run_id).execute()
        except Exception as e:
            logger.error(f"Error marking run {run_id} failed: {e}")

    def upsert_module_status(
        self,
        run_id: str,
        module_name: str,
        status: str,
        score: Optional[float] = None,
        max_score: Optional[float] = None,
        confidence: Optional[float] = None,
        error_information: Optional[Dict[str, Any]] = None,
        started_at: Optional[str] = None,
        completed_at: Optional[str] = None
    ) -> Optional[str]:
        """Record or update evaluation module status incrementally."""
        module_id = f"mod_{run_id}_{module_name}"
        data = {
            "run_id": run_id,
            "module_name": module_name,
            "status": status,
            "score": score,
            "max_score": max_score,
            "confidence": confidence,
            "error_information": error_information,
            "started_at": started_at,
            "completed_at": completed_at,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if self.use_mock:
            if not hasattr(self, "mock_modules"):
                self.mock_modules = {}
            if module_id not in self.mock_modules:
                data["id"] = module_id
                data["created_at"] = datetime.now(timezone.utc).isoformat()
            else:
                data = {**self.mock_modules[module_id], **data}
            self.mock_modules[module_id] = data
            return module_id

        try:
            client = self._get_client()
            if not client:
                return None
            res = client.table("evaluation_modules").upsert(
                data,
                on_conflict="run_id,module_name"
            ).select("id").single().execute()
            return res.data.get("id") if res.data else None
        except Exception as e:
            logger.error(f"Error persisting module status for {module_name}: {e}")
            return None

    def record_criterion_score(
        self,
        run_id: str,
        module_id: Optional[str],
        result: Any
    ) -> Optional[str]:
        """Record criterion score with strengths, weaknesses, recommendations."""
        res_dict = result.to_dict() if hasattr(result, "to_dict") else result
        category_key = res_dict.get("criterion")
        score_id = f"score_{run_id}_{category_key}"
        data = {
            "run_id": run_id,
            "module_id": module_id,
            "category_key": category_key,
            "criterion": category_key.replace("_", " ").title(),
            "score": res_dict.get("score", 0.0),
            "max_score": res_dict.get("maxScore", 0.0),
            "weight": res_dict.get("maxScore", 0.0),
            "confidence": res_dict.get("confidence", 1.0),
            "summary": res_dict.get("summary", ""),
            "strengths": res_dict.get("strengths", []),
            "weaknesses": res_dict.get("weaknesses", []),
            "recommendations": res_dict.get("recommendations", []),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if self.use_mock:
            if not hasattr(self, "mock_scores"):
                self.mock_scores = {}
            if score_id not in self.mock_scores:
                data["id"] = score_id
                data["created_at"] = datetime.now(timezone.utc).isoformat()
            else:
                data = {**self.mock_scores[score_id], **data}
            self.mock_scores[score_id] = data
            return score_id

        try:
            client = self._get_client()
            if not client:
                return None
            res = client.table("criterion_scores").upsert(
                data,
                on_conflict="run_id,category_key"
            ).select("id").single().execute()
            return res.data.get("id") if res.data else None
        except Exception as e:
            logger.error(f"Error recording criterion score for {category_key}: {e}")
            return None

    def record_evidence(
        self,
        run_id: str,
        criterion_score_id: Optional[str],
        evidence_list: List[Any]
    ):
        """Record raw evidence items."""
        if not evidence_list:
            return

        formatted = []
        for item in evidence_list:
            d = item.to_dict() if hasattr(item, "to_dict") else item
            formatted.append({
                "run_id": run_id,
                "criterion_score_id": criterion_score_id,
                "evidence_type": "deterministic_tool" if "timeout" not in d.get("metric", "") else "unmeasurable",
                "source": d.get("source", "evaluator"),
                "metric": d.get("metric", "unknown"),
                "value": d.get("value"),
                "interpretation": d.get("interpretation", ""),
                "raw_data": d.get("raw_data", {}),
                "citation_reference": d.get("citation_reference"),
                "timestamp": d.get("timestamp", datetime.now(timezone.utc).isoformat())
            })

        if self.use_mock:
            if not hasattr(self, "mock_evidence"):
                self.mock_evidence = []
            self.mock_evidence.extend(formatted)
            return

        try:
            client = self._get_client()
            if not client:
                return
            client.table("evidence").insert(formatted).execute()
        except Exception as e:
            logger.error(f"Error persisting evidence for run {run_id}: {e}")

    def record_report(self, run_id: str, project_id: str, report_dict: Dict[str, Any]):
        """Persist comprehensive evaluation report and score breakdown snapshot."""
        data = {
            "run_id": run_id,
            "project_id": project_id,
            "overall_score": report_dict.get("overall_score", 0.0),
            "rubric_version": report_dict.get("rubric_version", "1.0.0"),
            "weights_snapshot": report_dict.get("weights_snapshot", {}),
            "score_breakdown": report_dict.get("score_breakdown", {}),
            "executive_summary": report_dict.get("executive_summary", ""),
            "key_strengths": report_dict.get("key_strengths", []),
            "key_weaknesses": report_dict.get("key_weaknesses", []),
            "action_plan": report_dict.get("action_plan", []),
            "similar_projects": report_dict.get("similar_projects", []),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        if self.use_mock:
            self.mock_reports[run_id] = {
                "id": f"rep_{run_id}",
                "created_at": datetime.now(timezone.utc).isoformat(),
                **data
            }
            logger.info(f"Recorded mock report for run {run_id} (Score: {data['overall_score']})")
            return

        try:
            client = self._get_client()
            if not client:
                return
            client.table("reports").upsert(data, on_conflict="run_id").execute()
            logger.info(f"Persisted report to Supabase for run {run_id}")
        except Exception as e:
            logger.error(f"Error persisting report for run {run_id}: {e}")

    def recover_stale_jobs(self, stale_threshold_seconds: int = 900) -> int:
        """
        Detect and recover stranded jobs in 'running' status after worker crash or network partition.
        Requeues jobs under max retry limit (3), or marks them failed.
        """
        now = datetime.now(timezone.utc)
        recovered_count = 0

        if self.use_mock:
            for run_id, run in self.mock_runs.items():
                if run.get("status") == "running":
                    started_str = run.get("started_at")
                    if started_str:
                        try:
                            started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                            if (now - started_dt).total_seconds() > stale_threshold_seconds:
                                retries = run.get("retry_count", 0)
                                if retries < 3:
                                    run["status"] = "queued"
                                    run["worker_id"] = None
                                    run["retry_count"] = retries + 1
                                    run["error_information"] = {"reason": f"Worker recovered stale job (retry #{retries+1})"}
                                    logger.warning(f"[StaleJobRecovery] Requeued stalled mock run: {run_id} (retry #{retries+1})")
                                else:
                                    run["status"] = "failed"
                                    run["error_information"] = {"error": "Evaluation exceeded max retries after worker timeouts."}
                                    logger.error(f"[StaleJobRecovery] Marked run {run_id} as failed after {retries} retries.")
                                recovered_count += 1
                        except Exception:
                            pass
            return recovered_count

        try:
            client = self._get_client()
            if not client:
                return 0
            res = client.table("evaluation_runs").select("*").eq("status", "running").execute()
            for run in (res.data or []):
                started_str = run.get("started_at") or run.get("created_at")
                if started_str:
                    try:
                        started_dt = datetime.fromisoformat(started_str.replace("Z", "+00:00"))
                        if (now - started_dt).total_seconds() > stale_threshold_seconds:
                            retries = run.get("retry_count", 0)
                            if retries < 3:
                                client.table("evaluation_runs").update({
                                    "status": "queued",
                                    "worker_id": None,
                                    "retry_count": retries + 1,
                                    "error_information": {"reason": f"Worker recovered stale job (retry #{retries+1})"},
                                    "updated_at": now.isoformat()
                                }).eq("id", run["id"]).execute()
                                logger.warning(f"[StaleJobRecovery] Requeued stalled Supabase run: {run['id']} (retry #{retries+1})")
                            else:
                                client.table("evaluation_runs").update({
                                    "status": "failed",
                                    "error_information": {"error": "Evaluation exceeded max retries after worker timeouts."},
                                    "updated_at": now.isoformat()
                                }).eq("id", run["id"]).execute()
                                logger.error(f"[StaleJobRecovery] Marked Supabase run {run['id']} as failed after {retries} retries.")
                            recovered_count += 1
                    except Exception as parse_err:
                        logger.debug(f"Failed parsing run timestamp: {parse_err}")
            return recovered_count
        except Exception as e:
            logger.error(f"Error checking stale jobs: {e}")
            return 0

    def get_full_report(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Fetch complete evaluation bundle: run, project, modules, criterion_scores, evidence, and report."""
        if self.use_mock:
            run = self.mock_runs.get(run_id)
            if not run:
                return None
            sub = self.mock_submissions.get(run.get("submission_id"))
            proj = self.mock_projects.get(sub.get("project_id")) if sub else None
            modules = [m for m in self.mock_modules.values() if m.get("run_id") == run_id]
            scores = [s for s in self.mock_scores.values() if s.get("run_id") == run_id]
            evidence = [e for e in self.mock_evidence if e.get("run_id") == run_id]
            report = self.mock_reports.get(run_id)
            return {
                "run": run,
                "submission": sub,
                "project": proj,
                "modules": modules,
                "criterion_scores": scores,
                "evidence": evidence,
                "report": report
            }

        try:
            from supabase import create_client
            client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
            run_res = client.table("evaluation_runs").select("*, submissions(*, projects(*))").eq("id", run_id).maybeSingle().execute()
            if not run_res.data:
                return None
            modules_res = client.table("evaluation_modules").select("*").eq("run_id", run_id).execute()
            scores_res = client.table("criterion_scores").select("*").eq("run_id", run_id).execute()
            evidence_res = client.table("evidence").select("*").eq("run_id", run_id).execute()
            report_res = client.table("reports").select("*").eq("run_id", run_id).maybeSingle().execute()
            return {
                "run": run_res.data,
                "modules": modules_res.data or [],
                "criterion_scores": scores_res.data or [],
                "evidence": evidence_res.data or [],
                "report": report_res.data
            }
        except Exception as e:
            logger.error(f"Error fetching full report for run {run_id}: {e}")
            return None


