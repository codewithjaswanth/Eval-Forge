"use client";

import { useEffect, useState } from "react";
import {
  Clock,
  Cpu,
  CheckCircle2,
  XCircle,
  Code2,
  Layers,
  Box,
  FileCode,
  RotateCcw
} from "lucide-react";
import { EvaluationReportView } from "./evaluation-report";

interface LiveProgressProps {
  runId: string;
  repoUrl: string;
  onReset: () => void;
}

export function LiveProgress({ runId, repoUrl, onReset }: LiveProgressProps) {
  const [run, setRun] = useState<any>(null);
  const [modules, setModules] = useState<any[]>([]);
  const [criterionScores, setCriterionScores] = useState<any[]>([]);
  const [evidence, setEvidence] = useState<any[]>([]);
  const [report, setReport] = useState<any>(null);

  useEffect(() => {
    let intervalId: any = null;

    async function checkStatus() {
      try {
        const res = await fetch(`/api/submissions/${runId}/status`);
        if (res.ok) {
          const data = await res.json();
          if (data.run) {
            setRun(data.run);
            if (data.modules) setModules(data.modules);
            if (data.criterionScores) setCriterionScores(data.criterionScores);
            if (data.evidence) setEvidence(data.evidence);
            if (data.report) setReport(data.report);
            // Stop polling if completed or failed
            if (data.run.status === "completed" || data.run.status === "failed") {
              clearInterval(intervalId);
            }
          }
        }
      } catch (err) {
        console.error("Status polling error:", err);
      }
    }

    checkStatus();
    intervalId = setInterval(checkStatus, 2000);
    return () => clearInterval(intervalId);
  }, [runId]);

  const status = run?.status || "queued";
  const metadata = run?.submissions?.metadata || {};

  return (
    <div className="w-full max-w-4xl space-y-8 flex flex-col items-center">
      <div className="w-full bg-[#1B2336] border border-[#334155] rounded-xl p-6 sm:p-8 shadow-2xl space-y-6">
      {/* Top Header */}
      <div className="flex items-start justify-between border-b border-[#334155] pb-4">
        <div>
          <span className="text-xs font-mono text-[#94A3B8] uppercase tracking-wider">
            Evaluation Run ID
          </span>
          <div className="font-mono text-sm text-white font-medium break-all">{runId}</div>
          <div className="text-xs text-[#22C55E] mt-0.5 font-mono">{repoUrl}</div>
        </div>

        <button
          onClick={onReset}
          className="text-xs font-mono text-[#94A3B8] hover:text-white flex items-center gap-1.5 bg-[#0F172A] border border-[#334155] px-3 py-1.5 rounded-md transition-colors cursor-pointer"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>New Submission</span>
        </button>
      </div>

      {/* State Indicator */}
      <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-4 flex items-center gap-4">
        {status === "queued" && (
          <>
            <div className="p-3 bg-[#EAB308]/10 text-[#EAB308] rounded-lg animate-pulse">
              <Clock className="w-6 h-6" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">Status: Queued</div>
              <div className="text-xs text-[#94A3B8]">
                Waiting for Python worker daemon to atomically claim this job...
              </div>
            </div>
          </>
        )}

        {status === "running" && (
          <>
            <div className="p-3 bg-[#3B82F6]/10 text-[#3B82F6] rounded-lg animate-spin">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <div className="text-sm font-semibold text-white">Status: Ingesting & Analyzing</div>
              <div className="text-xs text-[#94A3B8]">
                Disposable workspace created. Performing shallow clone and metadata discovery...
              </div>
            </div>
          </>
        )}

        {status === "completed" && (
          <>
            <div className="p-3 bg-[#22C55E]/10 text-[#22C55E] rounded-lg">
              <CheckCircle2 className="w-6 h-6" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#22C55E]">Status: Ingestion Complete</div>
              <div className="text-xs text-[#94A3B8]">
                Normalized ProjectArtifact successfully extracted and registered in database.
              </div>
            </div>
          </>
        )}

        {status === "failed" && (
          <>
            <div className="p-3 bg-[#EF4444]/10 text-[#EF4444] rounded-lg">
              <XCircle className="w-6 h-6" />
            </div>
            <div>
              <div className="text-sm font-semibold text-[#EF4444]">Status: Pipeline Failed</div>
              <div className="text-xs text-[#EF4444]/80">
                {run?.error_information?.error || "Ingestion error occurred."}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Extracted Artifact Metadata (When Completed) */}
      {status === "completed" && metadata && Object.keys(metadata).length > 0 && (
        <div className="space-y-4 pt-2">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-mono text-white uppercase tracking-wider font-semibold">
              Discovered Project Artifacts
            </h3>
            {metadata.commit_sha && (
              <span className="text-xs font-mono bg-[#0F172A] border border-[#334155] px-2.5 py-1 rounded text-[#94A3B8]">
                SHA: {metadata.commit_sha.substring(0, 7)}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Languages */}
            <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-[#94A3B8] font-mono mb-2">
                <Code2 className="w-3.5 h-3.5 text-[#38BDF8]" /> Languages
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(metadata.detected_languages || []).map((lang: string) => (
                  <span key={lang} className="text-xs px-2 py-0.5 rounded bg-[#1E293B] text-white border border-[#475569]">
                    {lang}
                  </span>
                ))}
              </div>
            </div>

            {/* Frameworks */}
            <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-[#94A3B8] font-mono mb-2">
                <Layers className="w-3.5 h-3.5 text-[#A855F7]" /> Frameworks
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(metadata.detected_frameworks || []).length > 0 ? (
                  metadata.detected_frameworks.map((fw: string) => (
                    <span key={fw} className="text-xs px-2 py-0.5 rounded bg-[#1E293B] text-[#A855F7] border border-[#475569]">
                      {fw}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-[#64748B]">None detected</span>
                )}
              </div>
            </div>

            {/* Package Managers & Build */}
            <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-[#94A3B8] font-mono mb-2">
                <Box className="w-3.5 h-3.5 text-[#F59E0B]" /> Package Managers
              </div>
              <div className="flex flex-wrap gap-1.5">
                {(metadata.package_managers || []).map((pm: string) => (
                  <span key={pm} className="text-xs px-2 py-0.5 rounded bg-[#1E293B] text-[#F59E0B] border border-[#475569]">
                    {pm}
                  </span>
                ))}
              </div>
            </div>

            {/* Architecture Flags */}
            <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-3">
              <div className="flex items-center gap-1.5 text-xs text-[#94A3B8] font-mono mb-2">
                <FileCode className="w-3.5 h-3.5 text-[#22C55E]" /> Architecture
              </div>
              <div className="flex gap-3 text-xs">
                <span className={metadata.has_frontend ? "text-[#22C55E]" : "text-[#64748B]"}>
                  Frontend: {metadata.has_frontend ? "✓" : "✗"}
                </span>
                <span className={metadata.has_backend ? "text-[#22C55E]" : "text-[#64748B]"}>
                  Backend: {metadata.has_backend ? "✓" : "✗"}
                </span>
                <span className={metadata.has_readme ? "text-[#22C55E]" : "text-[#64748B]"}>
                  README: {metadata.has_readme ? "✓" : "✗"}
                </span>
              </div>
            </div>
          </div>

          {/* Files Summary */}
          <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-3 text-xs text-[#94A3B8] flex flex-wrap justify-between gap-2 font-mono">
            <span>Total Files: <strong className="text-white">{metadata.total_files || 0}</strong></span>
            <span>Test Files: <strong className="text-white">{metadata.test_files_count || 0}</strong></span>
            <span>CI Workflows: <strong className="text-white">{(metadata.ci_cd_workflows || []).length}</strong></span>
            <span>Docker: <strong className="text-white">{(metadata.docker_files || []).length > 0 ? "Yes" : "No"}</strong></span>
          </div>
        </div>
      )}
      </div>

      {/* Render full evaluation report if completed or scores available */}
      {(status === "completed" || criterionScores.length > 0) && (
        <EvaluationReportView
          run={run}
          modules={modules}
          criterionScores={criterionScores}
          evidence={evidence}
          report={report}
        />
      )}
    </div>
  );
}

