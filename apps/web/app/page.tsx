"use client";

import { useState } from "react";
import { SubmissionForm } from "@/components/submission-form";
import { LiveProgress } from "@/components/live-progress";
import { ShieldCheck, Terminal, Cpu, Search, CheckCircle } from "lucide-react";

export default function Home() {
  const [activeSubmission, setActiveSubmission] = useState<{
    runId: string;
    repoUrl: string;
    status: string;
  } | null>(null);

  return (
    <div className="min-h-screen bg-[#0F172A] text-[#F8FAFC] flex flex-col items-center">
      {/* Top Navigation */}
      <header className="w-full border-b border-[#334155] bg-[#0F172A]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
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
          </div>

          <div className="flex items-center gap-4 text-xs font-mono text-[#94A3B8]">
            <div className="hidden sm:flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-[#22C55E] animate-pulse"></span>
              <span>Worker Daemon Ready</span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 w-full max-w-6xl px-4 sm:px-6 py-12 flex flex-col items-center">
        {/* Hero Section */}
        <div className="text-center max-w-3xl mb-10 space-y-3">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#1B2336] border border-[#334155] text-xs font-mono text-[#22C55E]">
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Untrusted-Code Sandboxing & Deterministic Scoring</span>
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-white">
            AI-Powered Software Project Evaluation
          </h1>

          <p className="text-[#94A3B8] text-base sm:text-lg max-w-2xl mx-auto">
            Rigorous, evidence-backed evaluation scoring out of 100. Deterministic tools for code & performance metrics; structured LLMs for qualitative synthesis; verified web research for novelty.
          </p>

          {/* Core Principles Highlights */}
          <div className="pt-2 flex flex-wrap items-center justify-center gap-4 text-xs font-mono text-[#94A3B8]">
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

        {/* Interactive Workspace Area */}
        {activeSubmission ? (
          <LiveProgress
            runId={activeSubmission.runId}
            repoUrl={activeSubmission.repoUrl}
            onReset={() => setActiveSubmission(null)}
          />
        ) : (
          <SubmissionForm
            onSubmitted={(data) => {
              setActiveSubmission(data);
            }}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="w-full border-t border-[#334155] py-6 text-center text-xs font-mono text-[#64748B]">
        <div className="max-w-6xl mx-auto px-4">
          EvalForge Architecture Engine • Next.js 15 + Python 3.12 + Supabase PostgreSQL
        </div>
      </footer>
    </div>
  );
}
