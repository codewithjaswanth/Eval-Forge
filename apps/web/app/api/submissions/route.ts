import { NextRequest, NextResponse } from "next/server";
import { submissionSchema } from "@/lib/validators";
import { supabase, isSupabaseConfigured, localStore } from "@/lib/store";
import { globalSubmissionLimiter } from "@/lib/rate-limiter";
import { randomUUID } from "crypto";

export async function POST(req: NextRequest) {
  try {
    // 0. Extract client IP and enforce sliding window rate limiting
    const forwardedFor = req.headers.get("x-forwarded-for");
    const realIp = req.headers.get("x-real-ip");
    const clientIp = forwardedFor ? forwardedFor.split(",")[0].trim() : (realIp || "127.0.0.1");

    const rateCheck = globalSubmissionLimiter.check(clientIp);
    if (!rateCheck.allowed) {
      return NextResponse.json(
        {
          error: "Too many submission requests. Please wait before submitting another repository.",
          retryAfterSeconds: Math.ceil(rateCheck.resetTimeMs / 1000),
        },
        {
          status: 429,
          headers: {
            "Retry-After": Math.ceil(rateCheck.resetTimeMs / 1000).toString(),
            "X-RateLimit-Limit": "10",
            "X-RateLimit-Remaining": rateCheck.remaining.toString(),
          },
        }
      );
    }

    const json = await req.json();
    const result = submissionSchema.safeParse(json);

    if (!result.success) {
      return NextResponse.json(
        {
          error: "Validation failed",
          details: result.error.flatten().fieldErrors,
        },
        { status: 400 }
      );
    }

    const { repoUrl, liveUrl, description } = result.data;
    
    // Parse project name from GitHub URL (e.g. "https://github.com/owner/repo" -> "owner/repo")
    const match = repoUrl.match(/github\.com\/([^\/]+)\/([^\/]+)/);
    const projectName = match ? `${match[1]}/${match[2].replace(/\.git$/, "")}` : "Unknown Project";

    // 1. If Supabase is configured, use real database
    if (isSupabaseConfigured && supabase) {
      // Check if project exists or insert
      let projectId: string;
      const { data: existingProject } = await supabase
        .from("projects")
        .select("id")
        .eq("repo_url", repoUrl)
        .maybeSingle();

      if (existingProject) {
        projectId = existingProject.id;

        // Deduplication: Check if an active queued or running run already exists for this project
        const { data: activeRuns } = await supabase
          .from("evaluation_runs")
          .select("id, status, created_at, submission_id, submissions!inner(project_id)")
          .eq("submissions.project_id", projectId)
          .in("status", ["queued", "running"])
          .order("created_at", { ascending: false })
          .limit(1);

        if (activeRuns && activeRuns.length > 0) {
          const activeRun = activeRuns[0];
          return NextResponse.json(
            {
              success: true,
              projectId,
              submissionId: activeRun.submission_id,
              runId: activeRun.id,
              status: activeRun.status,
              repoUrl,
              createdAt: activeRun.created_at,
              deduplicated: true,
              message: "Reattached to existing active evaluation run.",
            },
            { status: 200 }
          );
        }

        // Optionally update live_url or description if provided
        if (liveUrl || description) {
          await supabase
            .from("projects")
            .update({
              live_url: liveUrl || null,
              description: description || null,
            })
            .eq("id", projectId);
        }
      } else {
        const { data: newProject, error: projErr } = await supabase
          .from("projects")
          .insert({
            name: projectName,
            repo_url: repoUrl,
            live_url: liveUrl || null,
            description: description || null,
            is_public: true,
          })
          .select("id")
          .single();

        if (projErr || !newProject) {
          return NextResponse.json(
            { error: "Failed to create project record", details: projErr?.message },
            { status: 500 }
          );
        }
        projectId = newProject.id;
      }

      // Create submission
      const { data: submission, error: subErr } = await supabase
        .from("submissions")
        .insert({
          project_id: projectId,
          branch: "main",
          status: "pending",
        })
        .select("id")
        .single();

      if (subErr || !submission) {
        return NextResponse.json(
          { error: "Failed to create submission", details: subErr?.message },
          { status: 500 }
        );
      }

      // Create evaluation_run with queued status
      const { data: run, error: runErr } = await supabase
        .from("evaluation_runs")
        .insert({
          submission_id: submission.id,
          rubric_version: "1.0.0",
          status: "queued",
        })
        .select("id, status, created_at")
        .single();

      if (runErr || !run) {
        return NextResponse.json(
          { error: "Failed to enqueue evaluation run", details: runErr?.message },
          { status: 500 }
        );
      }

      return NextResponse.json(
        {
          success: true,
          projectId,
          submissionId: submission.id,
          runId: run.id,
          status: run.status,
          repoUrl,
          createdAt: run.created_at,
        },
        { status: 201 }
      );
    }

    // 2. Local fallback memory store
    // Deduplication check for local memory store
    for (const p of localStore.projects.values()) {
      if (p.repo_url === repoUrl) {
        for (const r of localStore.evaluationRuns.values()) {
          const s = localStore.submissions.get(r.submission_id);
          if (s && s.project_id === p.id && (r.status === "queued" || r.status === "running")) {
            return NextResponse.json(
              {
                success: true,
                projectId: p.id,
                submissionId: s.id,
                runId: r.id,
                status: r.status,
                repoUrl,
                createdAt: r.created_at,
                deduplicated: true,
                message: "Reattached to existing active evaluation run.",
                mode: "local_memory",
              },
              { status: 200 }
            );
          }
        }
      }
    }

    const projectId = randomUUID();
    const submissionId = randomUUID();
    const runId = randomUUID();
    const now = new Date().toISOString();

    const projectData = {
      id: projectId,
      name: projectName,
      repo_url: repoUrl,
      live_url: liveUrl || null,
      description: description || null,
      is_public: true,
      created_at: now,
    };
    localStore.projects.set(projectId, projectData);

    const submissionData = {
      id: submissionId,
      project_id: projectId,
      branch: "main",
      status: "pending",
      metadata: {},
      created_at: now,
    };
    localStore.submissions.set(submissionId, submissionData);

    const runData = {
      id: runId,
      submission_id: submissionId,
      rubric_version: "1.0.0",
      status: "queued",
      worker_id: null,
      overall_score: null,
      confidence_score: null,
      error_information: null,
      started_at: null,
      completed_at: null,
      created_at: now,
    };
    localStore.evaluationRuns.set(runId, runData);

    return NextResponse.json(
      {
        success: true,
        projectId,
        submissionId,
        runId,
        status: "queued",
        repoUrl,
        createdAt: now,
        mode: "local_memory",
      },
      { status: 201 }
    );
  } catch (error: any) {
    return NextResponse.json(
      { error: "Internal server error", details: error?.message },
      { status: 500 }
    );
  }
}

export async function GET() {
  if (isSupabaseConfigured && supabase) {
    const { data, error } = await supabase
      .from("evaluation_runs")
      .select("*, submissions(*, projects(*))")
      .order("created_at", { ascending: false })
      .limit(10);

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    return NextResponse.json({ runs: data });
  }

  // Local fallback
  const runs = Array.from(localStore.evaluationRuns.values()).map((run) => {
    const sub = localStore.submissions.get(run.submission_id);
    const proj = sub ? localStore.projects.get(sub.project_id) : null;
    return {
      ...run,
      submission: sub,
      project: proj,
    };
  });

  return NextResponse.json({ runs });
}
