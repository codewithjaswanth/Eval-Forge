import { NextRequest, NextResponse } from "next/server";
import { supabase, isSupabaseConfigured, localStore } from "@/lib/store";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  if (isSupabaseConfigured && supabase) {
    try {
      const { data: run, error } = await supabase
        .from("evaluation_runs")
        .select("*, submissions(*, projects(*))")
        .eq("id", id)
        .maybeSingle();

      if (!error && run) {
        // Load related evaluation data
        const [modulesRes, scoresRes, evidenceRes, reportRes] = await Promise.all([
          supabase.from("evaluation_modules").select("*").eq("run_id", id),
          supabase.from("criterion_scores").select("*").eq("run_id", id),
          supabase.from("evidence").select("*").eq("run_id", id),
          supabase.from("reports").select("*").eq("run_id", id).maybeSingle(),
        ]);

        return NextResponse.json({
          run,
          modules: modulesRes.data || [],
          criterionScores: scoresRes.data || [],
          evidence: evidenceRes.data || [],
          report: reportRes.data || null,
        });
      }
    } catch (err) {
      console.warn("[Status] Supabase fetch failed, checking localStore:", err);
    }
  }

  // Local fallback
  const run = localStore.evaluationRuns.get(id);
  if (!run) {
    return NextResponse.json({ error: "Run not found" }, { status: 404 });
  }

  const submission = localStore.submissions.get(run.submission_id);
  const project = submission ? localStore.projects.get(submission.project_id) : null;

  const modules = Array.from(localStore.evaluationModules.values()).filter((m: any) => m.run_id === id);
  const criterionScores = Array.from(localStore.criterionScores.values()).filter((s: any) => s.run_id === id);
  const evidence = localStore.evidence.get(id) || [];
  const report = localStore.reports.get(id) || null;

  return NextResponse.json({
    run: {
      ...run,
      submissions: {
        ...submission,
        projects: project,
      },
    },
    modules,
    criterionScores,
    evidence,
    report,
  });
}
