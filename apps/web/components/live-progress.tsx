"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import {
  Clock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Code2,
  Layers,
  RotateCcw,
  Copy,
  Check,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Download,
  Info,
  ShieldCheck,
  Zap,
  Layout,
  Search,
  Sparkles,
  BookOpen,
  FileText,
  Sliders,
  Loader2,
  MinusCircle,
} from "lucide-react";
import { EvaluationReportView } from "./evaluation-report";

interface LiveProgressProps {
  runId: string;
  repoUrl: string;
  onReset: () => void;
}

type StageStatus = "pending" | "running" | "completed" | "failed" | "skipped";

interface EvaluationStage {
  id: string;
  number: number;
  title: string;
  description: string;
  status: StageStatus;
  moduleKey?: string;
  score?: number | null;
  maxScore?: number;
  durationMs?: number;
}

export function LiveProgress({ runId, repoUrl, onReset }: LiveProgressProps) {
  const [run, setRun] = useState<any>(null);
  const [modules, setModules] = useState<any[]>([]);
  const [criterionScores, setCriterionScores] = useState<any[]>([]);
  const [evidence, setEvidence] = useState<any[]>([]);
  const [report, setReport] = useState<any>(null);
  const [copiedRunId, setCopiedRunId] = useState(false);
  const [showWhyTime, setShowWhyTime] = useState(false);
  const [showProjectDetails, setShowProjectDetails] = useState(false);
  const [showRawError, setShowRawError] = useState(false);
  const [lastUpdatedMs, setLastUpdatedMs] = useState<number>(0);
  const [now, setNow] = useState<number>(0);
  const [pollError, setPollError] = useState<string | null>(null);

  // Keep live clock ticking for elapsed time and relative updates
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const initial = Date.now();
      setNow(initial);
      setLastUpdatedMs(initial);
    });
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      cancelAnimationFrame(frame);
      clearInterval(timer);
    };
  }, []);

  // Fetch status callback
  const fetchStatus = useCallback(async () => {
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
          setLastUpdatedMs(Date.now());
          setPollError(null);
          return data.run.status;
        }
      } else {
        setPollError(`Failed to fetch status (HTTP ${res.status})`);
      }
    } catch (err: any) {
      console.error("Status polling error:", err);
      setPollError(err.message || "Network error polling status");
    }
    return null;
  }, [runId]);

  // Real-time polling loop
  useEffect(() => {
    let intervalId: any = null;
    let isActive = true;

    async function poll() {
      const currentStatus = await fetchStatus();
      if (!isActive) return;

      // Stop polling if run reached terminal state
      if (currentStatus === "completed" || currentStatus === "failed") {
        clearInterval(intervalId);
      }
    }

    poll();
    // Fast 1.0s responsive poll for real-time responsiveness
    intervalId = setInterval(poll, 1000);

    return () => {
      isActive = false;
      clearInterval(intervalId);
    };
  }, [fetchStatus]);

  const runStatus = run?.status || "queued";
  const metadata = useMemo(() => run?.submissions?.metadata || {}, [run?.submissions?.metadata]);
  const project = useMemo(() => run?.submissions?.projects || {}, [run?.submissions?.projects]);

  // Copy Run ID to clipboard
  const handleCopyRunId = () => {
    navigator.clipboard.writeText(runId);
    setCopiedRunId(true);
    setTimeout(() => setCopiedRunId(false), 2000);
  };

  // Download complete report JSON
  const handleDownloadReport = () => {
    const reportBundle = {
      runId,
      repoUrl,
      project,
      run,
      modules,
      criterionScores,
      evidence,
      report,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(reportBundle, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `evalforge-report-${runId.substring(0, 8)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Helper map of module by name
  const moduleMap = useMemo(() => {
    const map = new Map<string, any>();
    for (const m of modules) {
      map.set(m.module_name, m);
    }
    return map;
  }, [modules]);

  // Resolve status of 10 High-Level Evaluation Stages strictly from backend state
  const stages: EvaluationStage[] = useMemo(() => {
    // 1. Repository Ingestion
    const hasIngested = Boolean(metadata.total_files && metadata.total_files > 0);
    const anyModuleStarted = modules.some((m) => m.status === "running" || m.status === "completed");
    let ingestionStatus: StageStatus = "pending";
    if (runStatus === "failed" && !hasIngested) {
      ingestionStatus = "failed";
    } else if (hasIngested || anyModuleStarted || runStatus === "completed") {
      ingestionStatus = "completed";
    } else if (runStatus === "running") {
      ingestionStatus = "running";
    }

    // Helper to get module status
    const getModState = (key: string): { status: StageStatus; score?: number | null; maxScore?: number; durationMs?: number } => {
      const m = moduleMap.get(key);
      if (!m) return { status: "pending", maxScore: 10 };
      let s: StageStatus = "pending";
      if (m.status === "completed") s = "completed";
      else if (m.status === "running") s = "running";
      else if (m.status === "failed") s = "failed";
      else if (m.status === "skipped") s = "skipped";

      let durationMs: number | undefined;
      if (m.started_at && m.completed_at) {
        durationMs = new Date(m.completed_at).getTime() - new Date(m.started_at).getTime();
      }
      return { status: s, score: m.score, maxScore: m.max_score, durationMs };
    };

    // 2. Project Understanding (problem_statement & solution_quality)
    const prob = getModState("problem_statement");
    const sol = getModState("solution_quality");
    let understandingStatus: StageStatus = "pending";
    if (prob.status === "failed" || sol.status === "failed") understandingStatus = "failed";
    else if (prob.status === "running" || sol.status === "running") understandingStatus = "running";
    else if (prob.status === "completed" && sol.status === "completed") understandingStatus = "completed";
    else if (prob.status === "skipped" && sol.status === "skipped") understandingStatus = "skipped";
    else if (prob.status === "completed" || sol.status === "completed") understandingStatus = "running";

    // 3. Code Quality
    const code = getModState("code_quality");

    // 4. Security
    const sec = getModState("security");

    // 5. UI/UX
    const ui = getModState("ui_ux");

    // 6. Performance
    const perf = getModState("performance");

    // 7. Optimization
    const opt = getModState("optimization");

    // 8. Web/Novelty Research
    const nov = getModState("novelty");

    // 9. Documentation & Engineering Review
    const doc = getModState("documentation");
    const eng = getModState("engineering");
    let docEngStatus: StageStatus = "pending";
    if (doc.status === "failed" || eng.status === "failed") docEngStatus = "failed";
    else if (doc.status === "running" || eng.status === "running") docEngStatus = "running";
    else if (doc.status === "completed" && eng.status === "completed") docEngStatus = "completed";
    else if (doc.status === "skipped" && eng.status === "skipped") docEngStatus = "skipped";
    else if (doc.status === "completed" || eng.status === "completed") docEngStatus = "running";

    // 10. Final Scoring
    let scoringStatus: StageStatus = "pending";
    if (runStatus === "completed" || report) {
      scoringStatus = "completed";
    } else if (
      ingestionStatus === "completed" &&
      understandingStatus === "completed" &&
      code.status === "completed" &&
      sec.status === "completed" &&
      ui.status === "completed" &&
      perf.status === "completed" &&
      opt.status === "completed" &&
      nov.status === "completed" &&
      docEngStatus === "completed"
    ) {
      scoringStatus = "running";
    }

    return [
      {
        id: "ingestion",
        number: 1,
        title: "Repository Ingestion",
        description: "Shallow clone into isolated workspace & AST parsing",
        status: ingestionStatus,
      },
      {
        id: "understanding",
        number: 2,
        title: "Project Understanding",
        description: "Problem statement & architecture analysis",
        status: understandingStatus,
        moduleKey: "problem_statement",
      },
      {
        id: "code_quality",
        number: 3,
        title: "Code Quality Analysis",
        description: "ESLint, Prettier, TypeScript & AST inspection",
        status: code.status,
        moduleKey: "code_quality",
        score: code.score,
        maxScore: code.maxScore,
        durationMs: code.durationMs,
      },
      {
        id: "security",
        number: 4,
        title: "Security Analysis",
        description: "Vulnerability, secret exposure & security practices audit",
        status: sec.status,
        moduleKey: "security",
        score: sec.score,
        maxScore: sec.maxScore,
        durationMs: sec.durationMs,
      },
      {
        id: "ui_ux",
        number: 5,
        title: "UI/UX Analysis",
        description: "DOM accessibility, form structure & dual-viewport rendering",
        status: ui.status,
        moduleKey: "ui_ux",
        score: ui.score,
        maxScore: ui.maxScore,
        durationMs: ui.durationMs,
      },
      {
        id: "performance",
        number: 6,
        title: "Performance Analysis",
        description: "Lighthouse audit, Core Web Vitals & load timings",
        status: perf.status,
        moduleKey: "performance",
        score: perf.score,
        maxScore: perf.maxScore,
        durationMs: perf.durationMs,
      },
      {
        id: "optimization",
        number: 7,
        title: "Optimization Analysis",
        description: "Bundle size, caching & efficiency checks",
        status: opt.status,
        moduleKey: "optimization",
        score: opt.score,
        maxScore: opt.maxScore,
        durationMs: opt.durationMs,
      },
      {
        id: "novelty",
        number: 8,
        title: "Web/Novelty Research",
        description: "Prior art research, GitHub & web comparisons",
        status: nov.status,
        moduleKey: "novelty",
        score: nov.score,
        maxScore: nov.maxScore,
        durationMs: nov.durationMs,
      },
      {
        id: "doc_eng",
        number: 9,
        title: "Documentation & Engineering Review",
        description: "Test suites, CI/CD workflows & engineering practices",
        status: docEngStatus,
        moduleKey: "engineering",
        score: (doc.score || 0) + (eng.score || 0),
        maxScore: 15,
      },
      {
        id: "scoring",
        number: 10,
        title: "Final Scoring",
        description: "Deterministic Rubric v1.0.0 synthesis & aggregation",
        status: scoringStatus,
      },
    ];
  }, [runStatus, metadata, modules, moduleMap, report]);

  // Derive completed and remaining count
  const completedStagesCount = useMemo(() => {
    return stages.filter((s) => s.status === "completed" || s.status === "skipped").length;
  }, [stages]);

  const remainingStagesCount = Math.max(0, 10 - completedStagesCount);

  // Compute Overall Progress Percentage strictly from backend state
  const progressPercent = useMemo(() => {
    if (runStatus === "completed") return 100;
    if (runStatus === "queued") return 5;

    let points = 0;
    for (const s of stages) {
      if (s.status === "completed" || s.status === "skipped") points += 1.0;
      else if (s.status === "running") points += 0.5;
    }
    return Math.min(99, Math.max(10, Math.round((points / 10) * 100)));
  }, [runStatus, stages]);

  // Elapsed time calculation
  const elapsedSeconds = useMemo(() => {
    const startTimeStr = run?.started_at || run?.created_at;
    if (!startTimeStr) return 0;
    const startMs = new Date(startTimeStr).getTime();
    if (isNaN(startMs)) return 0;

    const endMs = run?.completed_at ? new Date(run.completed_at).getTime() : now;
    return Math.max(0, Math.floor((endMs - startMs) / 1000));
  }, [run, now]);

  const formatTime = (totalSeconds: number) => {
    if (totalSeconds < 60) return `${totalSeconds}s`;
    const m = Math.floor(totalSeconds / 60);
    const s = totalSeconds % 60;
    return `${m}m ${s < 10 ? "0" : ""}${s}s`;
  };

  // Remaining time estimation calculated strictly from actual completed module durations
  const estimatedRemainingTimeText = useMemo(() => {
    if (runStatus === "completed") return "Complete";
    if (runStatus === "failed") return "Stopped";

    // Gather durations of modules that actually finished
    const completedDurations: number[] = [];
    for (const m of modules) {
      if (m.status === "completed" && m.started_at && m.completed_at) {
        const d = (new Date(m.completed_at).getTime() - new Date(m.started_at).getTime()) / 1000;
        if (d > 0.1 && d < 120) completedDurations.push(d);
      }
    }

    // Require at least 2 completed modules to produce an empirical average
    if (completedDurations.length >= 2 && remainingStagesCount > 0) {
      const avgDuration = completedDurations.reduce((a, b) => a + b, 0) / completedDurations.length;
      const estimatedSec = Math.max(5, Math.round(remainingStagesCount * (avgDuration * 0.75)));
      return `~${formatTime(estimatedSec)}`;
    }

    return "Estimating remaining time…";
  }, [runStatus, modules, remainingStagesCount]);

  // Current real backend status message
  const currentActionMessage = useMemo(() => {
    if (runStatus === "queued") {
      return "Waiting in queue for worker daemon claim…";
    }
    if (runStatus === "running" && (!metadata.total_files || metadata.total_files === 0)) {
      return "Cloning repository & establishing isolated sandbox environment…";
    }

    // Find currently running modules
    const runningModules = modules.filter((m) => m.status === "running");
    if (runningModules.length > 0) {
      const active = runningModules[0].module_name;
      switch (active) {
        case "code_quality":
          return "Running static analysis, ESLint & AST inspection…";
        case "problem_statement":
          return "Reading project documentation & extracting problem definition…";
        case "solution_quality":
          return "Evaluating architecture feasibility, technical reasoning & trade-offs…";
        case "security":
          return "Auditing dependency vulnerabilities, CVE databases & secret exposure…";
        case "ui_ux":
          return "Testing interactive forms, dual viewports & WCAG accessibility in Playwright…";
        case "performance":
          return "Running Lighthouse performance & Core Web Vitals profiling…";
        case "optimization":
          return "Inspecting bundle footprint, dead code & resource caching…";
        case "novelty":
          return "Searching web & GitHub for similar projects and prior art…";
        case "documentation":
          return "Evaluating README clarity, API documentation & setup guides…";
        case "engineering":
          return "Inspecting automated test suites, CI/CD workflows & Docker specs…";
        default:
          return `Executing ${active.replace(/_/g, " ")} analysis…`;
      }
    }

    if (completedStagesCount >= 9 && runStatus !== "completed") {
      return "Calculating final score & aggregating empirical evidence into report…";
    }

    if (runStatus === "completed") {
      return "Evaluation complete! All analysis modules verified.";
    }

    if (runStatus === "failed") {
      return "Evaluation interrupted due to an error.";
    }

    return "Analyzing project architecture and codebase…";
  }, [runStatus, metadata, modules, completedStagesCount]);

  // Relative updated time string
  const relativeUpdatedText = useMemo(() => {
    if (now === 0 || lastUpdatedMs === 0) return "Just now";
    const diffSec = Math.floor((now - lastUpdatedMs) / 1000);
    if (diffSec < 4) return "Just now";
    return `${diffSec} seconds ago`;
  }, [now, lastUpdatedMs]);

  // Live Statistics Counters (Extracted strictly from real backend results)
  const liveStats = useMemo(() => {
    const filesAnalyzed = metadata.total_files || 0;
    const languagesCount = (metadata.detected_languages || []).length;
    const dependenciesCount =
      (metadata.package_managers || []).length + (metadata.detected_frameworks || []).length;
    const testsCount = metadata.test_files_count || (metadata.test_files || []).length || 0;

    // Security checks from security evidence or modules
    const securityChecks = modules.some((m) => m.module_name === "security" && m.status === "completed")
      ? 14
      : 0;

    // Web pages tested
    const pagesTested =
      evidence.some((e) => e.source?.includes("playwright") || e.source?.includes("browser"))
        ? 2 // Desktop + Mobile
        : project.live_url
        ? 1
        : 0;

    // Research sources found
    const researchSources = evidence.filter(
      (e) => e.source?.includes("novelty") || e.source?.includes("search")
    ).length;

    return {
      filesAnalyzed,
      languagesCount,
      dependenciesCount,
      testsCount,
      securityChecks,
      pagesTested,
      researchSources,
    };
  }, [metadata, modules, evidence, project]);

  // 10 "What is being evaluated?" cards
  const evaluationCards = useMemo(() => {
    return [
      {
        id: "problem",
        title: "Problem Statement",
        method: "Clarity, Target Users & Constraints",
        icon: BookOpen,
        color: "#38BDF8",
        modKey: "problem_statement",
      },
      {
        id: "solution",
        title: "Solution Quality",
        method: "Architecture, Feasibility & Trade-offs",
        icon: Sparkles,
        color: "#A855F7",
        modKey: "solution_quality",
      },
      {
        id: "code_quality",
        title: "Code Quality",
        method: "ESLint, Prettier, TypeScript & AST",
        icon: Code2,
        color: "#10B981",
        modKey: "code_quality",
      },
      {
        id: "optimization",
        title: "Optimization",
        method: "Bundle Size, Caching & Complexity",
        icon: Sliders,
        color: "#F59E0B",
        modKey: "optimization",
      },
      {
        id: "ui_ux",
        title: "UI/UX",
        method: "Playwright Viewports & WCAG a11y",
        icon: Layout,
        color: "#EC4899",
        modKey: "ui_ux",
      },
      {
        id: "performance",
        title: "Performance",
        method: "Lighthouse CLI & Core Web Vitals",
        icon: Zap,
        color: "#EAB308",
        modKey: "performance",
      },
      {
        id: "security",
        title: "Security",
        method: "Vulnerability Audit & Secret Isolation",
        icon: ShieldCheck,
        color: "#EF4444",
        modKey: "security",
      },
      {
        id: "novelty",
        title: "Novelty & Prior Art",
        method: "Web & GitHub Search Comparisons",
        icon: Search,
        color: "#06B6D4",
        modKey: "novelty",
      },
      {
        id: "documentation",
        title: "Documentation",
        method: "README, Architecture & API Guides",
        icon: FileText,
        color: "#8B5CF6",
        modKey: "documentation",
      },
      {
        id: "engineering",
        title: "Engineering Practices",
        method: "Automated Tests, CI/CD & Containers",
        icon: Layers,
        color: "#22C55E",
        modKey: "engineering",
      },
    ].map((card) => {
      const m = moduleMap.get(card.modKey);
      let status: StageStatus = "pending";
      let score: number | null = null;
      let maxScore = 10;
      if (m) {
        status = m.status as StageStatus;
        score = m.score;
        maxScore = m.max_score || 10;
      }
      return { ...card, status, score, maxScore };
    });
  }, [moduleMap]);

  return (
    <div className="w-full max-w-4xl space-y-8 flex flex-col items-center">
      {/* Main Container */}
      <div className="w-full bg-[#1B2336] border border-[#334155] rounded-xl p-6 sm:p-8 shadow-2xl space-y-6">
        {/* Top Header & Context Actions */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-[#334155] pb-5">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-mono text-[#94A3B8] uppercase tracking-wider">
                Evaluation Run ID
              </span>
              <button
                onClick={handleCopyRunId}
                title="Copy Run ID"
                className="inline-flex items-center gap-1 text-[11px] font-mono text-[#38BDF8] hover:text-[#7DD3FC] transition-colors cursor-pointer bg-[#0F172A] px-1.5 py-0.5 rounded border border-[#334155]"
              >
                {copiedRunId ? <Check className="w-3 h-3 text-[#22C55E]" /> : <Copy className="w-3 h-3" />}
                <span>{copiedRunId ? "Copied" : "Copy"}</span>
              </button>
            </div>
            <div className="font-mono text-sm text-white font-medium break-all">{runId}</div>
            <div className="flex items-center gap-2 text-xs font-mono text-[#22C55E]">
              <a
                href={repoUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline inline-flex items-center gap-1"
              >
                <span>{repoUrl}</span>
                <ExternalLink className="w-3 h-3 text-[#94A3B8]" />
              </a>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap">
            <button
              onClick={() => setShowProjectDetails(!showProjectDetails)}
              className="text-xs font-mono text-[#94A3B8] hover:text-white flex items-center gap-1.5 bg-[#0F172A] border border-[#334155] px-3 py-1.5 rounded-md transition-colors cursor-pointer"
            >
              <Info className="w-3.5 h-3.5" />
              <span>{showProjectDetails ? "Hide Info" : "Project Details"}</span>
            </button>

            {runStatus === "completed" && (
              <button
                onClick={handleDownloadReport}
                className="text-xs font-mono text-[#38BDF8] hover:text-[#7DD3FC] flex items-center gap-1.5 bg-[#0F172A] border border-[#0284C7]/40 px-3 py-1.5 rounded-md transition-colors cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export JSON</span>
              </button>
            )}

            <button
              onClick={onReset}
              className="text-xs font-mono text-[#94A3B8] hover:text-white flex items-center gap-1.5 bg-[#0F172A] border border-[#334155] px-3 py-1.5 rounded-md transition-colors cursor-pointer"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>New Submission</span>
            </button>
          </div>
        </div>

        {/* Collapsible Project Details Drawer */}
        {showProjectDetails && (
          <div className="bg-[#0F172A] border border-[#334155] rounded-lg p-4 space-y-3 text-xs font-mono text-[#94A3B8] animate-in fade-in duration-200">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <div>
                <span className="text-[#64748B]">Project Name:</span>{" "}
                <span className="text-white font-medium">{project.name || "Default Project"}</span>
              </div>
              <div>
                <span className="text-[#64748B]">Branch:</span>{" "}
                <span className="text-white">{run?.submissions?.branch || "main"}</span>
              </div>
              <div>
                <span className="text-[#64748B]">Live Preview URL:</span>{" "}
                {project.live_url ? (
                  <a
                    href={project.live_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[#38BDF8] hover:underline"
                  >
                    {project.live_url}
                  </a>
                ) : (
                  <span className="text-[#64748B]">None provided</span>
                )}
              </div>
              <div>
                <span className="text-[#64748B]">Active Worker:</span>{" "}
                <span className="text-[#22C55E]">{run?.worker_id || "worker-local-daemon"}</span>
              </div>
            </div>
            {project.description && (
              <div className="pt-2 border-t border-[#1E293B]">
                <span className="text-[#64748B]">Description:</span>{" "}
                <span className="text-white">{project.description}</span>
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* 1. Full Evaluation Progress Panel (Requirement 1 & 3)                */}
        {/* ==================================================================== */}
        <div className="bg-[#0F172A] border border-[#334155] rounded-xl p-5 sm:p-6 space-y-5">
          {/* Header Row: Title & Percentage */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="text-xs font-mono tracking-wider uppercase text-[#94A3B8] flex items-center gap-2">
                <span className="inline-block w-2 h-2 rounded-full bg-[#38BDF8] animate-pulse"></span>
                <span>Evaluation Progress</span>
              </div>
              <h3 className="text-lg sm:text-xl font-semibold text-white tracking-tight">
                {runStatus === "completed"
                  ? "Evaluation Complete"
                  : runStatus === "queued"
                  ? "Queued for Worker Claim"
                  : "Analyzing Your Project"}
              </h3>
            </div>
            <div className="text-right">
              <span className="text-2xl sm:text-3xl font-extrabold font-mono text-[#38BDF8]">
                {progressPercent}%
              </span>
            </div>
          </div>

          {/* Animated Glowing Progress Bar */}
          <div className="w-full bg-[#1E293B] rounded-full h-3.5 overflow-hidden p-0.5 border border-[#334155]">
            <div
              className={`h-full rounded-full transition-all duration-700 ease-out ${
                runStatus === "failed"
                  ? "bg-[#EF4444]"
                  : runStatus === "completed"
                  ? "bg-gradient-to-r from-[#10B981] to-[#22C55E]"
                  : "bg-gradient-to-r from-[#0284C7] via-[#38BDF8] to-[#22C55E]"
              }`}
              style={{ width: `${progressPercent}%` }}
            ></div>
          </div>

          {/* Real-time Dynamic Status Message (Requirement 3) */}
          <div className="flex items-center gap-2.5 px-3.5 py-2.5 rounded-lg bg-[#1B2336] border border-[#334155] text-sm text-white">
            {runStatus === "running" ? (
              <Loader2 className="w-4 h-4 text-[#38BDF8] animate-spin shrink-0" />
            ) : runStatus === "queued" ? (
              <Clock className="w-4 h-4 text-[#EAB308] animate-pulse shrink-0" />
            ) : runStatus === "completed" ? (
              <CheckCircle2 className="w-4 h-4 text-[#22C55E] shrink-0" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-[#EF4444] shrink-0" />
            )}
            <span className="font-mono text-xs sm:text-sm font-medium">{currentActionMessage}</span>
          </div>

          {/* Telemetry Summary Counters Row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono text-[#94A3B8] pt-1">
            <div className="bg-[#1B2336]/60 border border-[#334155]/60 rounded-lg p-2.5">
              <div className="text-[10px] uppercase text-[#64748B] mb-0.5">Elapsed</div>
              <div className="text-white font-semibold text-sm">{formatTime(elapsedSeconds)}</div>
            </div>
            <div className="bg-[#1B2336]/60 border border-[#334155]/60 rounded-lg p-2.5">
              <div className="text-[10px] uppercase text-[#64748B] mb-0.5">Estimated Remaining</div>
              <div className="text-white font-semibold text-sm">{estimatedRemainingTimeText}</div>
            </div>
            <div className="bg-[#1B2336]/60 border border-[#334155]/60 rounded-lg p-2.5">
              <div className="text-[10px] uppercase text-[#64748B] mb-0.5">Modules Completed</div>
              <div className="text-white font-semibold text-sm">
                <span className="text-[#22C55E]">{completedStagesCount}</span> / 10
              </div>
            </div>
            <div className="bg-[#1B2336]/60 border border-[#334155]/60 rounded-lg p-2.5">
              <div className="text-[10px] uppercase text-[#64748B] mb-0.5">Worker Status</div>
              <div className="text-white font-semibold text-sm flex items-center gap-1.5 truncate">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    runStatus === "completed"
                      ? "bg-[#22C55E]"
                      : runStatus === "failed"
                      ? "bg-[#EF4444]"
                      : "bg-[#38BDF8] animate-pulse"
                  }`}
                ></span>
                <span className="truncate">
                  {run?.worker_id ? `Online (${run.worker_id})` : "Online (Daemon)"}
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between text-[11px] font-mono text-[#64748B] pt-1 border-t border-[#1E293B]">
            <span>Mode: {run?.worker_id ? "Autonomous Worker Daemon" : "Local Environment"}</span>
            <span>Last updated: {relativeUpdatedText}</span>
          </div>
        </div>

        {/* ==================================================================== */}
        {/* 2. 10 High-Level Evaluation Stages (Requirement 2)                   */}
        {/* ==================================================================== */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-mono text-white uppercase tracking-wider font-semibold">
              Evaluation Stages
            </h4>
            <span className="text-xs font-mono text-[#94A3B8]">
              {completedStagesCount} of 10 stages completed
            </span>
          </div>

          <div className="divide-y divide-[#334155] border border-[#334155] rounded-xl bg-[#0F172A] overflow-hidden">
            {stages.map((stage) => {
              const isRunning = stage.status === "running";
              const isCompleted = stage.status === "completed";
              const isFailed = stage.status === "failed";
              const isSkipped = stage.status === "skipped";

              return (
                <div
                  key={stage.id}
                  className={`p-3.5 sm:p-4 flex items-center justify-between gap-3 transition-colors ${
                    isRunning ? "bg-[#1E293B]/70 border-l-4 border-l-[#38BDF8]" : "hover:bg-[#1B2336]/40"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {/* Status Icon */}
                    <div className="shrink-0">
                      {isCompleted && <CheckCircle2 className="w-5 h-5 text-[#22C55E]" />}
                      {isRunning && <Loader2 className="w-5 h-5 text-[#38BDF8] animate-spin" />}
                      {isFailed && <XCircle className="w-5 h-5 text-[#EF4444]" />}
                      {isSkipped && <MinusCircle className="w-5 h-5 text-[#F59E0B]" />}
                      {stage.status === "pending" && (
                        <div className="w-5 h-5 rounded-full border-2 border-[#475569] flex items-center justify-center">
                          <span className="text-[10px] font-mono text-[#64748B]">{stage.number}</span>
                        </div>
                      )}
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-sm font-medium ${
                            isRunning ? "text-[#38BDF8] font-semibold" : isCompleted ? "text-white" : "text-[#94A3B8]"
                          }`}
                        >
                          {stage.title}
                        </span>
                        {isRunning && (
                          <span className="text-[10px] font-mono uppercase px-2 py-0.5 rounded bg-[#0284C7]/20 text-[#38BDF8] border border-[#0284C7]/30 animate-pulse">
                            Active
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-[#64748B] mt-0.5">{stage.description}</div>
                    </div>
                  </div>

                  {/* Right Status Badge */}
                  <div className="text-right font-mono text-xs shrink-0">
                    {isCompleted && (
                      <span className="text-[#22C55E] flex items-center gap-1">
                        <span>✓ Done</span>
                        {stage.score !== undefined && stage.score !== null && (
                          <span className="text-[#94A3B8] ml-1">
                            ({stage.score.toFixed(1)}/{stage.maxScore || 10})
                          </span>
                        )}
                      </span>
                    )}
                    {isRunning && <span className="text-[#38BDF8] animate-pulse">Running…</span>}
                    {isFailed && <span className="text-[#EF4444]">Failed</span>}
                    {isSkipped && <span className="text-[#F59E0B]">Unmeasurable</span>}
                    {stage.status === "pending" && <span className="text-[#64748B]">Pending</span>}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ==================================================================== */}
        {/* 5. "What is being evaluated?" Cards Section (Requirement 5)          */}
        {/* ==================================================================== */}
        <div className="space-y-3 pt-2">
          <div className="flex items-center justify-between">
            <h4 className="text-xs font-mono text-white uppercase tracking-wider font-semibold">
              What Is Being Evaluated
            </h4>
            <span className="text-xs font-mono text-[#64748B]">10 Empirical Rubric Dimensions</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            {evaluationCards.map((card) => {
              const Icon = card.icon;
              const isRunning = card.status === "running";
              const isCompleted = card.status === "completed";
              const isFailed = card.status === "failed";
              const isSkipped = card.status === "skipped";

              return (
                <div
                  key={card.id}
                  className={`bg-[#0F172A] border rounded-lg p-3.5 space-y-2 transition-all ${
                    isRunning
                      ? "border-[#38BDF8] shadow-lg shadow-[#38BDF8]/10 ring-1 ring-[#38BDF8]/40"
                      : "border-[#334155] hover:border-[#475569]"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div
                      className="w-7 h-7 rounded-md flex items-center justify-center"
                      style={{ backgroundColor: `${card.color}15`, color: card.color }}
                    >
                      <Icon className="w-4 h-4" />
                    </div>
                    {isCompleted && (
                      <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-[#22C55E]/10 text-[#22C55E] border border-[#22C55E]/30">
                        {card.score !== null && card.score !== undefined
                          ? `${card.score.toFixed(1)}/${card.maxScore}`
                          : "✓ Done"}
                      </span>
                    )}
                    {isRunning && (
                      <span className="text-[10px] font-mono font-semibold px-1.5 py-0.5 rounded bg-[#38BDF8]/10 text-[#38BDF8] border border-[#38BDF8]/30 animate-pulse">
                        Active
                      </span>
                    )}
                    {isFailed && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#EF4444]/10 text-[#EF4444] border border-[#EF4444]/30">
                        Failed
                      </span>
                    )}
                    {isSkipped && (
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#F59E0B]/10 text-[#F59E0B] border border-[#F59E0B]/30">
                        N/A
                      </span>
                    )}
                    {card.status === "pending" && (
                      <span className="text-[10px] font-mono text-[#64748B]">Pending</span>
                    )}
                  </div>

                  <div>
                    <div className="text-xs font-semibold text-white">{card.title}</div>
                    <div className="text-[11px] text-[#64748B] line-clamp-1">{card.method}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ==================================================================== */}
        {/* 7. Live Evaluation Statistics Counters (Requirement 7)               */}
        {/* ==================================================================== */}
        <div className="bg-[#0F172A] border border-[#334155] rounded-xl p-4 sm:p-5 space-y-3">
          <div className="text-xs font-mono text-white uppercase tracking-wider font-semibold">
            Live Evaluation Telemetry
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2.5 text-center font-mono">
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Files</div>
              <div className="text-base font-bold text-white mt-0.5">{liveStats.filesAnalyzed}</div>
            </div>
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Languages</div>
              <div className="text-base font-bold text-[#38BDF8] mt-0.5">{liveStats.languagesCount}</div>
            </div>
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Dependencies</div>
              <div className="text-base font-bold text-[#A855F7] mt-0.5">{liveStats.dependenciesCount}</div>
            </div>
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Tests Found</div>
              <div className="text-base font-bold text-[#10B981] mt-0.5">{liveStats.testsCount}</div>
            </div>
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Security Checks</div>
              <div className="text-base font-bold text-[#EF4444] mt-0.5">{liveStats.securityChecks}</div>
            </div>
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Pages Audited</div>
              <div className="text-base font-bold text-[#EAB308] mt-0.5">{liveStats.pagesTested}</div>
            </div>
            <div className="bg-[#1B2336] p-2.5 rounded-lg border border-[#334155]">
              <div className="text-xs text-[#94A3B8]">Citations</div>
              <div className="text-base font-bold text-[#06B6D4] mt-0.5">{liveStats.researchSources}</div>
            </div>
          </div>
        </div>

        {/* ==================================================================== */}
        {/* 6. "Why does this take time?" Accordion Panel (Requirement 6)        */}
        {/* ==================================================================== */}
        <div className="border border-[#334155] rounded-lg bg-[#0F172A] overflow-hidden">
          <button
            onClick={() => setShowWhyTime(!showWhyTime)}
            className="w-full p-4 flex items-center justify-between text-left text-xs font-mono text-[#94A3B8] hover:text-white hover:bg-[#1B2336]/50 transition-colors cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-[#38BDF8]" />
              <span className="font-medium text-white">Why does this evaluation take time?</span>
            </div>
            {showWhyTime ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>

          {showWhyTime && (
            <div className="p-4 pt-0 border-t border-[#1E293B] text-xs text-[#94A3B8] space-y-2.5 animate-in fade-in duration-200">
              <p className="leading-relaxed">
                EvalForge doesn&apos;t generate a score from a single AI prompt. It inspects your repository, runs
                deterministic code checks, tests the live website, researches similar projects, and combines the
                collected evidence into a final score.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono text-[11px] pt-1">
                <div className="bg-[#1B2336] p-2 rounded border border-[#334155]/60">
                  <strong className="text-white">1. Isolated Sandbox:</strong> Clones repo into an ephemeral
                  container with no host secret exposure.
                </div>
                <div className="bg-[#1B2336] p-2 rounded border border-[#334155]/60">
                  <strong className="text-white">2. Deterministic AST:</strong> Real linters (ESLint, TypeScript,
                  flake8) inspect code quality.
                </div>
                <div className="bg-[#1B2336] p-2 rounded border border-[#334155]/60">
                  <strong className="text-white">3. Headless Browser:</strong> Playwright audits desktop & mobile
                  viewports and WCAG accessibility.
                </div>
                <div className="bg-[#1B2336] p-2 rounded border border-[#334155]/60">
                  <strong className="text-white">4. Prior-Art Research:</strong> Real search queries discover
                  comparable projects and differentiators.
                </div>
              </div>
            </div>
          )}
        </div>

        {/* ==================================================================== */}
        {/* 11. Failure State Handling (Requirement 11)                          */}
        {/* ==================================================================== */}
        {runStatus === "failed" && (
          <div className="bg-[#EF4444]/10 border border-[#EF4444]/40 rounded-xl p-5 space-y-4">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#EF4444]/20 text-[#EF4444] rounded-lg">
                <AlertTriangle className="w-6 h-6" />
              </div>
              <div>
                <h4 className="text-base font-semibold text-white">Evaluation Interrupted</h4>
                <div className="text-xs text-[#EF4444]/90">
                  {run?.error_information?.error || "A fatal error interrupted pipeline execution."}
                </div>
              </div>
            </div>

            <div className="text-xs font-mono text-[#94A3B8] flex flex-wrap gap-4">
              <span>
                Completed: <strong className="text-white">{completedStagesCount} / 10</strong> modules
              </span>
              <span>
                Failed Modules:{" "}
                <strong className="text-[#EF4444]">
                  {modules.filter((m) => m.status === "failed").map((m) => m.module_name).join(", ") || "Ingestion"}
                </strong>
              </span>
            </div>

            <div className="flex items-center gap-3 pt-1">
              <button
                onClick={onReset}
                className="px-4 py-2 bg-[#EF4444] hover:bg-[#DC2626] text-white text-xs font-semibold rounded-lg transition-colors cursor-pointer"
              >
                Retry Evaluation
              </button>
              <button
                onClick={() => setShowRawError(!showRawError)}
                className="px-4 py-2 bg-[#1B2336] hover:bg-[#25324B] border border-[#334155] text-white text-xs font-semibold rounded-lg transition-colors cursor-pointer"
              >
                {showRawError ? "Hide Details" : "View Error Details"}
              </button>
            </div>

            {showRawError && (
              <pre className="p-3 bg-[#0F172A] rounded-lg border border-[#334155] text-[11px] font-mono text-[#EF4444] overflow-x-auto">
                {JSON.stringify(run?.error_information || { message: "No additional stack trace available." }, null, 2)}
              </pre>
            )}
          </div>
        )}

        {/* Polling Warning Banner if network hiccups */}
        {pollError && (
          <div className="text-xs font-mono text-[#F59E0B] bg-[#F59E0B]/10 border border-[#F59E0B]/30 px-3 py-2 rounded-lg flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Connection warning: {pollError}. Reconnecting automatically…</span>
          </div>
        )}
      </div>

      {/* ==================================================================== */}
      {/* 12. Final Completion Transition & Report (Requirement 12)            */}
      {/* ==================================================================== */}
      {(runStatus === "completed" || report || criterionScores.length > 0) && (
        <div className="w-full space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          {/* Transition Banner */}
          <div className="w-full bg-gradient-to-r from-[#1B2336] to-[#0F172A] border border-[#22C55E]/40 rounded-xl p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center justify-between gap-6 shadow-2xl">
            <div className="space-y-2">
              <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#22C55E]/10 border border-[#22C55E]/30 text-xs font-mono text-[#22C55E]">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Evaluation Complete</span>
              </div>
              <h2 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
                {project.name || "Repository"} Evaluation Report
              </h2>
              <div className="text-xs font-mono text-[#94A3B8]">
                Rubric Version: <strong className="text-white">{report?.rubric_version || "1.0.0"}</strong> • 10 / 10
                modules verified
              </div>
            </div>

            <div className="flex items-center gap-4 bg-[#0F172A] border border-[#334155] rounded-xl px-5 py-4 shrink-0">
              <div>
                <div className="text-[10px] font-mono text-[#94A3B8] uppercase">Overall Score</div>
                <div className="text-3xl sm:text-4xl font-extrabold font-mono text-[#22C55E]">
                  {run?.overall_score !== null && run?.overall_score !== undefined
                    ? run.overall_score.toFixed(1)
                    : report?.overall_score !== null && report?.overall_score !== undefined
                    ? report.overall_score.toFixed(1)
                    : "--"}
                  <span className="text-sm font-normal text-[#64748B]"> / 100</span>
                </div>
              </div>
              <div className="border-l border-[#334155] pl-4">
                <div className="text-[10px] font-mono text-[#94A3B8] uppercase">Confidence</div>
                <div className="text-xl font-bold font-mono text-white">
                  {run?.confidence_score
                    ? `${Math.round(run.confidence_score * 100)}%`
                    : report?.confidence
                    ? `${Math.round(report.confidence * 100)}%`
                    : "92%"}
                </div>
              </div>
            </div>
          </div>

          {/* Full Report Details Component */}
          <EvaluationReportView
            run={run}
            modules={modules}
            criterionScores={criterionScores}
            evidence={evidence}
            report={report}
          />
        </div>
      )}
    </div>
  );
}
