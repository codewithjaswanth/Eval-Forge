"use client";

import { useState } from "react";
import {
  Award,
  CheckCircle2,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  FileCode,
  ShieldAlert,
  Zap,
  Layout,
  Gauge,
  BookOpen,
  Sparkles,
  GitBranch,
  ExternalLink,
  Layers
} from "lucide-react";

interface EvaluationReportProps {
  run: any;
  modules: any[];
  criterionScores: any[];
  evidence: any[];
  report: any;
}

const CATEGORY_ICONS: Record<string, any> = {
  problem_statement: BookOpen,
  solution_quality: Layers,
  code_quality: FileCode,
  optimization: Zap,
  ui_ux: Layout,
  performance: Gauge,
  security: ShieldAlert,
  novelty: Sparkles,
  documentation: BookOpen,
  engineering_practices: GitBranch,
};

export function EvaluationReportView({
  run,
  modules: _modules,
  criterionScores: _criterionScores,
  evidence,
  report,
}: EvaluationReportProps) {
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const overallScore = report?.overall_score ?? run?.overall_score ?? 0;
  const confidence = report?.confidence ?? run?.confidence_score ?? 1.0;
  const rubricVersion = report?.rubric_version || run?.rubric_version || "1.0.0";
  const scoreBreakdown = report?.score_breakdown || {};
  const executiveSummary = report?.executive_summary || "Evaluation completed successfully.";
  const keyStrengths = report?.key_strengths || [];
  const keyWeaknesses = report?.key_weaknesses || [];
  const actionPlan = report?.action_plan || [];

  // Group evidence by category_key or criterion_score_id
  const evidenceByCategory: Record<string, any[]> = {};
  for (const item of evidence) {
    const key = item.criterion_score_id || item.source || "general";
    if (!evidenceByCategory[key]) evidenceByCategory[key] = [];
    evidenceByCategory[key].push(item);
  }

  // Get score color
  const getScoreColor = (score: number) => {
    if (score >= 80) return "text-[#22C55E] border-[#22C55E]/40 bg-[#22C55E]/10";
    if (score >= 65) return "text-[#38BDF8] border-[#38BDF8]/40 bg-[#38BDF8]/10";
    if (score >= 50) return "text-[#EAB308] border-[#EAB308]/40 bg-[#EAB308]/10";
    return "text-[#EF4444] border-[#EF4444]/40 bg-[#EF4444]/10";
  };

  const getProgressColor = (score: number, max: number) => {
    const pct = (score / Math.max(1, max)) * 100;
    if (pct >= 80) return "bg-[#22C55E]";
    if (pct >= 65) return "bg-[#38BDF8]";
    if (pct >= 50) return "bg-[#EAB308]";
    return "bg-[#EF4444]";
  };

  const toggleExpand = (catKey: string) => {
    setExpandedCategory((prev) => (prev === catKey ? null : catKey));
  };

  return (
    <div className="w-full space-y-6">
      {/* 1. Executive Summary & Overall Score Card */}
      <div className="bg-[#0F172A] border border-[#334155] rounded-xl p-6 sm:p-8 flex flex-col sm:flex-row items-center justify-between gap-6 shadow-xl">
        <div className="space-y-2 text-center sm:text-left">
          <div className="flex items-center justify-center sm:justify-start gap-2">
            <span className="text-xs font-mono uppercase tracking-wider text-[#94A3B8]">
              Final Evaluation Verdict
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#1E293B] text-[#94A3B8] border border-[#334155]">
              Rubric v{rubricVersion}
            </span>
          </div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Engineering Analysis Report</h2>
          <p className="text-sm text-[#94A3B8] max-w-xl leading-relaxed">{executiveSummary}</p>
        </div>

        <div className="flex flex-col items-center justify-center">
          <div
            className={`w-32 h-32 rounded-2xl border-2 flex flex-col items-center justify-center shadow-lg transition-transform ${getScoreColor(
              overallScore
            )}`}
          >
            <span className="text-4xl font-extrabold tracking-tighter">{overallScore.toFixed(1)}</span>
            <span className="text-xs font-mono font-medium opacity-80">/ 100.0</span>
          </div>
          <div className="mt-2 text-[11px] font-mono text-[#94A3B8] flex items-center gap-1.5">
            <Award className="w-3.5 h-3.5 text-[#22C55E]" />
            <span>{(confidence * 100).toFixed(0)}% Confidence</span>
          </div>
        </div>
      </div>

      {/* 2. Key Strengths, Weaknesses & Action Plan */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Strengths */}
        <div className="bg-[#0F172A] border border-[#334155] rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#22C55E]">
            <CheckCircle2 className="w-4 h-4" />
            <span>Key Engineering Strengths</span>
          </div>
          {keyStrengths.length > 0 ? (
            <ul className="space-y-2 text-xs text-[#CBD5E1]">
              {keyStrengths.map((str: string, i: number) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-[#22C55E] mt-0.5">•</span>
                  <span>{str}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[#64748B]">No specific strengths recorded.</p>
          )}
        </div>

        {/* Weaknesses */}
        <div className="bg-[#0F172A] border border-[#334155] rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#EF4444]">
            <AlertTriangle className="w-4 h-4" />
            <span>Identified Weaknesses</span>
          </div>
          {keyWeaknesses.length > 0 ? (
            <ul className="space-y-2 text-xs text-[#CBD5E1]">
              {keyWeaknesses.map((weak: string, i: number) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-[#EF4444] mt-0.5">•</span>
                  <span>{weak}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[#64748B]">No critical weaknesses identified.</p>
          )}
        </div>

        {/* Action Plan */}
        <div className="bg-[#0F172A] border border-[#334155] rounded-xl p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-[#F59E0B]">
            <Zap className="w-4 h-4" />
            <span>Actionable Recommendations</span>
          </div>
          {actionPlan.length > 0 ? (
            <ul className="space-y-2 text-xs text-[#CBD5E1]">
              {actionPlan.map((rec: string, i: number) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="text-[#F59E0B] mt-0.5">→</span>
                  <span>{rec}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[#64748B]">No recommendations recorded.</p>
          )}
        </div>
      </div>

      {/* 3. Category Score Breakdown (10 Criteria) */}
      <div className="space-y-3">
        <div className="flex items-center justify-between pb-1">
          <h3 className="text-sm font-mono uppercase tracking-wider text-white font-semibold">
            10-Criterion Evaluation Breakdown
          </h3>
          <span className="text-xs text-[#94A3B8] font-mono">Deterministic Weights</span>
        </div>

        <div className="grid grid-cols-1 gap-3">
          {Object.entries(scoreBreakdown).map(([catKey, data]: [string, any]) => {
            const IconComponent = CATEGORY_ICONS[catKey] || FileCode;
            const isExpanded = expandedCategory === catKey;
            const catEvidence = evidence.filter((e) => e.criterion_score_id?.includes(catKey) || e.source?.toLowerCase().includes(catKey));

            return (
              <div
                key={catKey}
                className="bg-[#0F172A] border border-[#334155] rounded-xl overflow-hidden transition-colors hover:border-[#475569]"
              >
                {/* Header Row */}
                <div
                  onClick={() => toggleExpand(catKey)}
                  className="p-4 flex items-center justify-between cursor-pointer select-none"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-9 h-9 rounded-lg bg-[#1E293B] border border-[#334155] flex items-center justify-center text-[#38BDF8]">
                      <IconComponent className="w-4 h-4" />
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-white flex items-center gap-2">
                        <span>{data.category_name}</span>
                        {data.status === "unmeasurable" && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-[#334155] text-[#94A3B8]">
                            Unmeasurable
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[#94A3B8] max-w-md truncate">{data.summary}</div>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <div className="text-sm font-bold text-white font-mono">
                        {data.normalized_score.toFixed(1)} <span className="text-xs text-[#64748B]">/ {data.weight}</span>
                      </div>
                      <div className="w-24 bg-[#1E293B] h-1.5 rounded-full overflow-hidden mt-1">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${getProgressColor(
                            data.normalized_score,
                            data.weight
                          )}`}
                          style={{
                            width: `${Math.min(100, (data.normalized_score / Math.max(1, data.weight)) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>

                    <div className="text-[#94A3B8]">
                      {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-[#334155] bg-[#141E33] p-5 space-y-4 text-xs">
                    {/* Strengths & Weaknesses */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      {data.strengths?.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="font-mono text-[11px] text-[#22C55E] uppercase font-semibold">Strengths</span>
                          <ul className="space-y-1 text-[#CBD5E1]">
                            {data.strengths.map((s: string, idx: number) => (
                              <li key={idx} className="flex items-start gap-1.5">
                                <span className="text-[#22C55E]">•</span>
                                <span>{s}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {data.weaknesses?.length > 0 && (
                        <div className="space-y-1.5">
                          <span className="font-mono text-[11px] text-[#EF4444] uppercase font-semibold">Weaknesses</span>
                          <ul className="space-y-1 text-[#CBD5E1]">
                            {data.weaknesses.map((w: string, idx: number) => (
                              <li key={idx} className="flex items-start gap-1.5">
                                <span className="text-[#EF4444]">•</span>
                                <span>{w}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>

                    {/* Recommendations */}
                    {data.recommendations?.length > 0 && (
                      <div className="space-y-1.5 pt-2 border-t border-[#334155]/60">
                        <span className="font-mono text-[11px] text-[#F59E0B] uppercase font-semibold">
                          Recommendations
                        </span>
                        <ul className="space-y-1 text-[#CBD5E1]">
                          {data.recommendations.map((r: string, idx: number) => (
                            <li key={idx} className="flex items-start gap-1.5">
                              <span className="text-[#F59E0B]">→</span>
                              <span>{r}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Empirical Evidence Details */}
                    {catEvidence.length > 0 && (
                      <div className="space-y-2 pt-2 border-t border-[#334155]/60">
                        <span className="font-mono text-[11px] text-[#38BDF8] uppercase font-semibold">
                          Empirical Evidence & Tool Measurements
                        </span>
                        <div className="space-y-2">
                          {catEvidence.map((ev: any, evIdx: number) => (
                            <div
                              key={evIdx}
                              className="bg-[#0F172A] border border-[#334155] rounded-lg p-3 font-mono text-[11px] space-y-1"
                            >
                              <div className="flex items-center justify-between text-[#94A3B8]">
                                <span className="text-white font-medium">{ev.metric}</span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#1E293B] border border-[#334155]">
                                  {ev.source}
                                </span>
                              </div>
                              <div className="text-[#CBD5E1]">{ev.interpretation}</div>
                              {ev.value !== undefined && (
                                <div className="text-xs text-[#22C55E] pt-1">
                                  Value: {typeof ev.value === "object" ? JSON.stringify(ev.value) : String(ev.value)}
                                </div>
                              )}
                              {ev.citation_reference?.url && (
                                <div className="pt-1">
                                  <a
                                    href={ev.citation_reference.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 text-[#38BDF8] hover:underline text-[10px]"
                                  >
                                    <ExternalLink className="w-3 h-3" />
                                    <span>{ev.citation_reference.url}</span>
                                  </a>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
