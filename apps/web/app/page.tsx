"use client";

import { useState, useEffect } from "react";
import { SubmissionForm } from "@/components/submission-form";
import { LiveProgress } from "@/components/live-progress";
import { ShieldCheck, Terminal, Cpu, Search, CheckCircle, Clock, ExternalLink } from "lucide-react";

interface ActiveSubmission {
  runId: string;
  repoUrl: string;
  status: string;
}

export default function Home() {
  const [activeSubmission, setActiveSubmission] = useState<ActiveSubmission | null>(null);
  const [recentRuns, setRecentRuns] = useState<ActiveSubmission[]>([]);

  // Restore active submission from URL query parameter (?runId=...) or localStorage
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search);
      const urlRunId = params.get("runId");

      const storedRecents = localStorage.getItem("evalforge_recent_runs");
      const parsedRecents = storedRecents ? JSON.parse(storedRecents) : [];

      const storedActive = localStorage.getItem("evalforge_active_run");
      const parsedActive = storedActive ? JSON.parse(storedActive) : null;

      // Defer state updates to avoid synchronous cascading effect renders
      setTimeout(() => {
        if (parsedRecents.length > 0) {
          setRecentRuns(parsedRecents);
        }

        if (urlRunId) {
          fetch(`/api/submissions/${urlRunId}/status`)
            .then((res) => (res.ok ? res.json() : null))
            .then((data) => {
              if (data?.run) {
                const restored: ActiveSubmission = {
                  runId: urlRunId,
                  repoUrl: data.run.submissions?.projects?.repo_url || "https://github.com/repository",
                  status: data.run.status,
                };
                setActiveSubmission(restored);
              }
            })
            .catch((e) => console.error("Could not restore URL runId:", e));
        } else if (parsedActive?.runId) {
          setActiveSubmission(parsedActive);
          window.history.replaceState(null, "", `?runId=${parsedActive.runId}`);
        }
      }, 0);
    } catch (e) {
      console.error("Storage error:", e);
    }
  }, []);

  // Handle new submission
  const handleSubmitted = (data: ActiveSubmission) => {
    setActiveSubmission(data);
    try {
      localStorage.setItem("evalforge_active_run", JSON.stringify(data));
      window.history.pushState(null, "", `?runId=${data.runId}`);

      // Add to recent runs list
      setRecentRuns((prev) => {
        const filtered = prev.filter((r) => r.runId !== data.runId);
        const updated = [data, ...filtered].slice(0, 5);
        localStorage.setItem("evalforge_recent_runs", JSON.stringify(updated));
        return updated;
      });
    } catch (e) {
      console.error("Storage write error:", e);
    }
  };

  // Reset to submission form
  const handleReset = () => {
    setActiveSubmission(null);
    try {
      localStorage.removeItem("evalforge_active_run");
      window.history.pushState(null, "", window.location.pathname);
    } catch (e) {
      console.error("Storage clear error:", e);
    }
  };

  return (
    <div className="min-h-screen bg-[#0F172A] text-[#F8FAFC] flex flex-col items-center">
      {/* Top Navigation */}
      <header className="w-full border-b border-[#334155] bg-[#0F172A]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <button
            onClick={handleReset}
            className="flex items-center gap-2.5 hover:opacity-90 transition-opacity cursor-pointer text-left"
          >
            <div className="w-8 h-8 rounded-lg bg-[#22C55E]/10 border border-[#22C55E]/30 flex items-center justify-center text-[#22C55E]">
              <Terminal className="w-4 h-4" />
            </div>
            <div>
              <span className="font-mono font-bold tracking-tight text-white text-lg">
                Eval<span className="text-[#22C55E]">Forge</span>
              </span>
              <span className="ml-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#1E293B] text-[#94A3B8] border border-[#334155]">
                v1.0.0
              </span>
            </div>
          </button>

          <div className="flex items-center gap-4 text-xs font-mono text-[#94A3B8]">
            {activeSubmission && (
              <button
                onClick={handleReset}
                className="hidden sm:inline-flex items-center gap-1.5 bg-[#1B2336] hover:bg-[#243047] border border-[#334155] px-3 py-1.5 rounded-md text-white transition-colors cursor-pointer"
              >
                <span>New Evaluation</span>
              </button>
            )}
            <div className="flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#22C55E] animate-pulse"></span>
              <span className="hidden sm:inline">Worker Engine Online</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-6xl px-4 sm:px-6 py-10 flex flex-col items-center">
        {!activeSubmission && (
          <div className="text-center max-w-3xl mb-8 space-y-3">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#1B2336] border border-[#334155] text-xs font-mono text-[#22C55E]">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Grounded Empirical Audits & Deterministic Scoring</span>
            </div>

            <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
              AI-Powered Software Project Evaluation
            </h1>

            <p className="text-[#94A3B8] text-base sm:text-lg max-w-2xl mx-auto">
              Rigorous, evidence-backed evaluation scored out of 100. Deterministic tools for code & live performance; structured LLMs for qualitative reasoning; verified web research for novelty.
            </p>

            {/* Core Highlights */}
            <div className="pt-2 flex flex-wrap items-center justify-center gap-3 text-xs font-mono text-[#94A3B8]">
              <div className="flex items-center gap-1 bg-[#1B2336]/60 px-2.5 py-1 rounded border border-[#334155]/60">
                <Cpu className="w-3.5 h-3.5 text-[#38BDF8]" /> Deterministic Linters & AST
              </div>
              <div className="flex items-center gap-1 bg-[#1B2336]/60 px-2.5 py-1 rounded border border-[#334155]/60">
                <Search className="w-3.5 h-3.5 text-[#A855F7]" /> Verified Citations
              </div>
              <div className="flex items-center gap-1 bg-[#1B2336]/60 px-2.5 py-1 rounded border border-[#334155]/60">
                <CheckCircle className="w-3.5 h-3.5 text-[#22C55E]" /> Isolated Sandboxing
              </div>
            </div>
          </div>
        )}

        {/* Dynamic Workspace */}
        {activeSubmission ? (
          <LiveProgress
            runId={activeSubmission.runId}
            repoUrl={activeSubmission.repoUrl}
            onReset={handleReset}
          />
        ) : (
          <div className="w-full flex flex-col items-center space-y-8">
            <SubmissionForm onSubmitted={handleSubmitted} />

            {/* Recent Evaluations Drawer if user has prior runs */}
            {recentRuns.length > 0 && (
              <div className="w-full max-w-2xl bg-[#1B2336]/60 border border-[#334155] rounded-xl p-4 sm:p-5 space-y-3">
                <div className="text-xs font-mono text-[#94A3B8] uppercase tracking-wider font-semibold flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5 text-[#38BDF8]" />
                  <span>Recent Evaluations on this Device</span>
                </div>
                <div className="divide-y divide-[#334155]/50">
                  {recentRuns.map((r) => (
                    <button
                      key={r.runId}
                      onClick={() => handleSubmitted(r)}
                      className="w-full py-2.5 flex items-center justify-between text-left hover:text-[#38BDF8] transition-colors cursor-pointer group"
                    >
                      <div className="truncate pr-4">
                        <div className="text-xs font-mono text-white group-hover:text-[#38BDF8] truncate">
                          {r.repoUrl}
                        </div>
                        <div className="text-[11px] font-mono text-[#64748B]">Run: {r.runId}</div>
                      </div>
                      <div className="text-xs font-mono text-[#38BDF8] flex items-center gap-1 shrink-0">
                        <span>Resume</span>
                        <ExternalLink className="w-3 h-3" />
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="w-full border-t border-[#334155] py-6 text-center text-xs font-mono text-[#64748B]">
        <div className="max-w-6xl mx-auto px-4">
          EvalForge Architecture Engine • Next.js 16 + Python 3.11 + Supabase PostgreSQL
        </div>
      </footer>
    </div>
  );
}
