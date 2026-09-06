"use client";

import { useState } from "react";
import { GitBranch, Globe, FileText, AlertCircle, ArrowRight, Loader2, CheckCircle2 } from "lucide-react";

interface SubmissionFormProps {
  onSubmitted: (data: { runId: string; repoUrl: string; status: string }) => void;
}

export function SubmissionForm({ onSubmitted }: SubmissionFormProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [liveUrl, setLiveUrl] = useState("");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submissionFeedback, setSubmissionFeedback] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isSubmitting) return;

    setError(null);

    // Client-side format validation
    const trimmedRepo = repoUrl.trim();
    const githubRegex = /^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(\/)?$/;
    if (!githubRegex.test(trimmedRepo)) {
      setError("Please provide a valid GitHub repository URL (e.g. https://github.com/owner/repo)");
      return;
    }

    setIsSubmitting(true);
    setSubmissionFeedback("Registering submission and dispatching to worker queue…");

    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repoUrl: trimmedRepo,
          liveUrl: liveUrl.trim() || undefined,
          description: description.trim() || undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Submission failed. Please verify your repository URL.");
      }

      setSubmissionFeedback("Evaluation started! Initializing isolated workspace…");

      // Small delay for smooth visual transition
      setTimeout(() => {
        onSubmitted({
          runId: data.runId,
          repoUrl: data.repoUrl,
          status: data.status,
        });
      }, 350);
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred during submission.");
      setIsSubmitting(false);
      setSubmissionFeedback(null);
    }
  }

  const fillExampleRepo = (url: string, live?: string, desc?: string) => {
    setRepoUrl(url);
    if (live) setLiveUrl(live);
    if (desc) setDescription(desc);
  };

  return (
    <div className="w-full max-w-2xl bg-[#1B2336] border border-[#334155] rounded-xl p-6 sm:p-8 shadow-2xl space-y-6">
      <div>
        <div className="flex items-center gap-2 text-[#22C55E] text-xs font-mono tracking-wider uppercase mb-1">
          <CheckCircle2 className="w-4 h-4" /> Ready for Analysis
        </div>
        <h2 className="text-xl sm:text-2xl font-semibold text-white tracking-tight">
          Submit Project for Evaluation
        </h2>
        <p className="text-[#94A3B8] text-sm mt-1">
          Enter a public repository to trigger isolated ingestion, stack detection, deterministic code audits, and live Playwright verification.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Repo URL Input */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-1.5 font-mono">
            GitHub Repository URL <span className="text-[#EF4444]">*</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#64748B]">
              <GitBranch className="w-4 h-4" />
            </div>
            <input
              type="url"
              required
              disabled={isSubmitting}
              placeholder="https://github.com/owner/repository"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="w-full bg-[#0F172A] border border-[#334155] focus:border-[#22C55E] focus:ring-1 focus:ring-[#22C55E] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#475569] outline-none font-mono transition-colors disabled:opacity-50"
            />
          </div>

          {/* Quick example pills */}
          <div className="flex items-center gap-2 mt-2 text-[11px] font-mono text-[#64748B]">
            <span>Try example:</span>
            <button
              type="button"
              onClick={() => fillExampleRepo("https://github.com/codewithjaswanth/Eval-Forge.git", "https://evalforge.dev", "EvalForge automated engineering evaluation platform")}
              className="text-[#38BDF8] hover:underline cursor-pointer bg-[#0F172A] px-2 py-0.5 rounded border border-[#334155]"
            >
              Eval-Forge
            </button>
            <button
              type="button"
              onClick={() => fillExampleRepo("https://github.com/facebook/react.git")}
              className="text-[#38BDF8] hover:underline cursor-pointer bg-[#0F172A] px-2 py-0.5 rounded border border-[#334155]"
            >
              React
            </button>
          </div>
        </div>

        {/* Live Website URL Input */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-1.5 font-mono">
            Deployed Website URL <span className="text-[#64748B] font-normal normal-case">(Optional - enables Lighthouse & Playwright)</span>
          </label>
          <div className="relative">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-[#64748B]">
              <Globe className="w-4 h-4" />
            </div>
            <input
              type="url"
              disabled={isSubmitting}
              placeholder="https://your-project.vercel.app"
              value={liveUrl}
              onChange={(e) => setLiveUrl(e.target.value)}
              className="w-full bg-[#0F172A] border border-[#334155] focus:border-[#22C55E] focus:ring-1 focus:ring-[#22C55E] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#475569] outline-none font-mono transition-colors disabled:opacity-50"
            />
          </div>
        </div>

        {/* Description Input */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-1.5 font-mono">
            Project Description <span className="text-[#64748B] font-normal normal-case">(Optional - assists problem & solution reasoning)</span>
          </label>
          <div className="relative">
            <div className="absolute top-3 left-3.5 flex items-start pointer-events-none text-[#64748B]">
              <FileText className="w-4 h-4" />
            </div>
            <textarea
              rows={3}
              disabled={isSubmitting}
              placeholder="Describe the problem, target audience, and architecture highlights..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-[#0F172A] border border-[#334155] focus:border-[#22C55E] focus:ring-1 focus:ring-[#22C55E] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#475569] outline-none transition-colors resize-none disabled:opacity-50"
            />
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="p-3 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-lg flex items-center gap-2 text-xs text-[#EF4444]">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Immediate Submission Feedback */}
        {submissionFeedback && (
          <div className="p-3 bg-[#38BDF8]/10 border border-[#38BDF8]/30 rounded-lg flex items-center gap-2 text-xs font-mono text-[#38BDF8] animate-pulse">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" />
            <span>{submissionFeedback}</span>
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-[#22C55E] hover:bg-[#16A34A] disabled:opacity-50 disabled:cursor-not-allowed text-[#0F172A] font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-all font-mono text-sm shadow-lg shadow-[#22C55E]/10 cursor-pointer"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Dispatching Evaluation Run…</span>
            </>
          ) : (
            <>
              <span>Begin Full Project Evaluation</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>
    </div>
  );
}
