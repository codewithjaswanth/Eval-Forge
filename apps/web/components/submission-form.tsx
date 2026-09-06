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
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    // Client-side quick check
    const githubRegex = /^https?:\/\/(www\.)?github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+(\/)?$/;
    if (!githubRegex.test(repoUrl.trim())) {
      setError("Please provide a valid GitHub repository URL (e.g. https://github.com/owner/repo)");
      return;
    }

    setIsSubmitting(true);
    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          repoUrl: repoUrl.trim(),
          liveUrl: liveUrl.trim() || undefined,
          description: description.trim() || undefined,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || "Submission failed. Please verify your repository URL.");
      }

      onSubmitted({
        runId: data.runId,
        repoUrl: data.repoUrl,
        status: data.status,
      });
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="w-full max-w-2xl bg-[#1B2336] border border-[#334155] rounded-xl p-6 sm:p-8 shadow-2xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-[#22C55E] text-xs font-mono tracking-wider uppercase mb-1">
          <CheckCircle2 className="w-4 h-4" /> Ready for Analysis
        </div>
        <h2 className="text-xl sm:text-2xl font-semibold text-white tracking-tight">
          Submit Project for Evaluation
        </h2>
        <p className="text-[#94A3B8] text-sm mt-1">
          Enter a public repository to trigger isolated ingestion, stack detection, and deterministic evaluation.
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
              placeholder="https://github.com/owner/repository"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              className="w-full bg-[#0F172A] border border-[#334155] focus:border-[#22C55E] focus:ring-1 focus:ring-[#22C55E] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#475569] outline-none font-mono transition-colors"
            />
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
              placeholder="https://my-project.vercel.app"
              value={liveUrl}
              onChange={(e) => setLiveUrl(e.target.value)}
              className="w-full bg-[#0F172A] border border-[#334155] focus:border-[#22C55E] focus:ring-1 focus:ring-[#22C55E] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#475569] outline-none font-mono transition-colors"
            />
          </div>
        </div>

        {/* Project Description Input */}
        <div>
          <label className="block text-xs font-medium uppercase tracking-wider text-[#94A3B8] mb-1.5 font-mono">
            Project Description & Stated Problem <span className="text-[#64748B] font-normal normal-case">(Optional)</span>
          </label>
          <div className="relative">
            <div className="absolute top-3 left-3.5 pointer-events-none text-[#64748B]">
              <FileText className="w-4 h-4" />
            </div>
            <textarea
              rows={3}
              placeholder="Describe the target audience, problem statement, or unique architecture constraints..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full bg-[#0F172A] border border-[#334155] focus:border-[#22C55E] focus:ring-1 focus:ring-[#22C55E] rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-[#475569] outline-none transition-colors"
            />
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-3 bg-[#EF4444]/10 border border-[#EF4444]/30 rounded-lg flex items-start gap-2.5 text-sm text-[#EF4444]">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Submit Action */}
        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-[#22C55E] hover:bg-[#16A34A] text-[#0F172A] font-semibold py-3 px-4 rounded-lg flex items-center justify-center gap-2 transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-[#22C55E]/10"
        >
          {isSubmitting ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Validating & Enqueueing...</span>
            </>
          ) : (
            <>
              <span>Queue Project Evaluation</span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>
    </div>
  );
}
