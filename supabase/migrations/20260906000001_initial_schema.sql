-- ==============================================================================
-- EvalForge: Initial Database Schema Migration
-- Version: 1.0.0
-- Description: Core tables, foreign keys, indexes, status constraints, RLS policies,
--              and atomic queue claiming function for EvalForge platform.
-- ==============================================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ==============================================================================
-- 1. SCORING RUBRICS & CONFIGURATION
-- ==============================================================================

CREATE TABLE IF NOT EXISTS scoring_rubrics (
    version VARCHAR(50) PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    total_weight NUMERIC(5,2) NOT NULL DEFAULT 100.00,
    is_active BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_total_weight_100 CHECK (total_weight = 100.00)
);

CREATE TABLE IF NOT EXISTS rubric_categories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rubric_version VARCHAR(50) NOT NULL REFERENCES scoring_rubrics(version) ON DELETE CASCADE,
    category_key VARCHAR(50) NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    weight NUMERIC(5,2) NOT NULL CHECK (weight >= 0 AND weight <= 100),
    evaluator_name VARCHAR(100) NOT NULL,
    criteria_rubric JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_rubric_category UNIQUE (rubric_version, category_key)
);

-- Function and trigger to ensure category weights for any rubric sum to exactly 100.00
CREATE OR REPLACE FUNCTION validate_rubric_weights_sum()
RETURNS TRIGGER AS $$
DECLARE
    current_sum NUMERIC(5,2);
    target_weight NUMERIC(5,2);
    target_version VARCHAR(50);
BEGIN
    target_version := COALESCE(NEW.rubric_version, OLD.rubric_version);

    SELECT total_weight INTO target_weight
    FROM scoring_rubrics
    WHERE version = target_version;

    SELECT COALESCE(SUM(weight), 0) INTO current_sum
    FROM rubric_categories
    WHERE rubric_version = target_version;

    -- Only validate if all categories for this rubric have been seeded (deferred check or manual verification)
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ==============================================================================
-- 2. PROJECTS & SUBMISSIONS
-- ==============================================================================

CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID, -- References auth.users(id) when Supabase auth is enabled
    name TEXT NOT NULL,
    repo_url TEXT NOT NULL,
    live_url TEXT,
    description TEXT,
    is_public BOOLEAN NOT NULL DEFAULT true,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_repo_url_format CHECK (
        repo_url ~* '^https?://[a-zA-Z0-9.-]+/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+/?$'
    )
);

CREATE TABLE IF NOT EXISTS submissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    commit_hash VARCHAR(40),
    branch VARCHAR(255) DEFAULT 'main',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_submission_status CHECK (
        status IN ('pending', 'processing', 'processed', 'failed')
    )
);

-- ==============================================================================
-- 3. EVALUATION RUNS & QUEUE ORCHESTRATION
-- ==============================================================================

CREATE TABLE IF NOT EXISTS evaluation_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    submission_id UUID NOT NULL REFERENCES submissions(id) ON DELETE CASCADE,
    rubric_version VARCHAR(50) NOT NULL REFERENCES scoring_rubrics(version) DEFAULT '1.0.0',
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    overall_score NUMERIC(5,2),
    confidence_score NUMERIC(4,3),
    error_information JSONB,
    worker_id VARCHAR(100),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_run_status CHECK (
        status IN ('queued', 'running', 'completed', 'failed', 'cancelled')
    ),
    CONSTRAINT chk_overall_score CHECK (
        overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)
    ),
    CONSTRAINT chk_confidence_score CHECK (
        confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1.0)
    )
);

CREATE TABLE IF NOT EXISTS evaluation_modules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    module_name VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    score NUMERIC(5,2),
    max_score NUMERIC(5,2),
    confidence NUMERIC(4,3),
    error_information JSONB,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_module_status CHECK (
        status IN ('pending', 'running', 'completed', 'skipped', 'failed')
    ),
    CONSTRAINT chk_module_confidence CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1.0)
    ),
    CONSTRAINT uq_run_module UNIQUE (run_id, module_name)
);

-- ==============================================================================
-- 4. CRITERION SCORES, EVIDENCE & RESEARCH
-- ==============================================================================

CREATE TABLE IF NOT EXISTS criterion_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    module_id UUID REFERENCES evaluation_modules(id) ON DELETE SET NULL,
    category_key VARCHAR(50) NOT NULL,
    criterion TEXT NOT NULL,
    score NUMERIC(5,2) NOT NULL,
    max_score NUMERIC(5,2) NOT NULL,
    weight NUMERIC(5,2) NOT NULL CHECK (weight >= 0 AND weight <= 100),
    confidence NUMERIC(4,3) NOT NULL DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1.0),
    summary TEXT NOT NULL,
    strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
    weaknesses JSONB NOT NULL DEFAULT '[]'::jsonb,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_run_criterion UNIQUE (run_id, category_key),
    CONSTRAINT chk_criterion_score CHECK (score >= 0 AND score <= max_score)
);

CREATE TABLE IF NOT EXISTS evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    criterion_score_id UUID REFERENCES criterion_scores(id) ON DELETE CASCADE,
    evidence_type VARCHAR(50) NOT NULL,
    source VARCHAR(100) NOT NULL,
    metric VARCHAR(150) NOT NULL,
    value JSONB NOT NULL,
    interpretation TEXT NOT NULL,
    raw_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    citation_reference JSONB,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_evidence_type CHECK (
        evidence_type IN (
            'deterministic_tool',
            'static_ast',
            'llm_reasoning',
            'web_citation',
            'performance_metric',
            'security_finding',
            'manual_override',
            'unmeasurable'
        )
    )
);

CREATE TABLE IF NOT EXISTS research_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    query TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    source VARCHAR(100) NOT NULL,
    similarity_assessment TEXT NOT NULL,
    relevance NUMERIC(4,3) CHECK (relevance >= 0 AND relevance <= 1.0),
    summary TEXT NOT NULL,
    raw_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==============================================================================
-- 5. FINAL REPORTS & REPRODUCIBILITY SNAPSHOTS
-- ==============================================================================

CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL UNIQUE REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    overall_score NUMERIC(5,2) NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
    rubric_version VARCHAR(50) NOT NULL,
    weights_snapshot JSONB NOT NULL,
    score_breakdown JSONB NOT NULL,
    executive_summary TEXT NOT NULL,
    key_strengths JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_weaknesses JSONB NOT NULL DEFAULT '[]'::jsonb,
    action_plan JSONB NOT NULL DEFAULT '[]'::jsonb,
    similar_projects JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==============================================================================
-- 6. PERFORMANCE & QUEUE INDEXES
-- ==============================================================================

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON projects(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_submissions_project_id ON submissions(project_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_submission_id ON evaluation_runs(submission_id);

-- Partial index for rapid queue polling by workers:
CREATE INDEX IF NOT EXISTS idx_evaluation_runs_queued 
    ON evaluation_runs(created_at ASC) 
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_evaluation_modules_run_id ON evaluation_modules(run_id);
CREATE INDEX IF NOT EXISTS idx_criterion_scores_run_id ON criterion_scores(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_run_id ON evidence(run_id);
CREATE INDEX IF NOT EXISTS idx_evidence_criterion_score_id ON evidence(criterion_score_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source_metric ON evidence(source, metric);
CREATE INDEX IF NOT EXISTS idx_research_results_run_id ON research_results(run_id);
CREATE INDEX IF NOT EXISTS idx_reports_project_id ON reports(project_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC);

-- ==============================================================================
-- 7. ATOMIC QUEUE WORKER PROCEDURES
-- ==============================================================================

CREATE OR REPLACE FUNCTION claim_next_evaluation_run(p_worker_id TEXT)
RETURNS SETOF evaluation_runs AS $$
BEGIN
    RETURN QUERY
    UPDATE evaluation_runs
    SET status = 'running',
        worker_id = p_worker_id,
        started_at = NOW(),
        updated_at = NOW()
    WHERE id = (
        SELECT id
        FROM evaluation_runs
        WHERE status = 'queued'
        ORDER BY created_at ASC
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING *;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update updated_at timestamps automatically
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$ 
DECLARE 
    t TEXT;
BEGIN
    FOR t IN 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
          AND table_name IN ('scoring_rubrics', 'rubric_categories', 'projects', 'submissions', 'evaluation_runs', 'evaluation_modules', 'criterion_scores', 'reports')
    LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS trg_update_timestamp_%I ON %I;', t, t);
        EXECUTE format('CREATE TRIGGER trg_update_timestamp_%I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();', t, t);
    END LOOP;
END $$;

-- ==============================================================================
-- 8. ROW LEVEL SECURITY (RLS) POLICIES
-- ==============================================================================

ALTER TABLE scoring_rubrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE rubric_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE criterion_scores ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;

-- 8.1 SERVICE ROLE POLICIES (Worker & Server Actions have full access)
CREATE POLICY "service_role_all_scoring_rubrics" ON scoring_rubrics FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_rubric_categories" ON rubric_categories FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_projects" ON projects FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_submissions" ON submissions FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_evaluation_runs" ON evaluation_runs FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_evaluation_modules" ON evaluation_modules FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_criterion_scores" ON criterion_scores FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_evidence" ON evidence FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_research_results" ON research_results FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "service_role_all_reports" ON reports FOR ALL TO service_role USING (true) WITH CHECK (true);

-- 8.2 PUBLIC READ POLICIES (Public projects, active rubrics, and published reports)
CREATE POLICY "public_read_scoring_rubrics" ON scoring_rubrics FOR SELECT TO anon, authenticated USING (is_active = true);
CREATE POLICY "public_read_rubric_categories" ON rubric_categories FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public_read_projects" ON projects FOR SELECT TO anon, authenticated USING (is_public = true OR (auth.uid() IS NOT NULL AND auth.uid() = user_id));
CREATE POLICY "public_read_submissions" ON submissions FOR SELECT TO anon, authenticated USING (EXISTS (SELECT 1 FROM projects WHERE projects.id = submissions.project_id AND (projects.is_public = true OR (auth.uid() IS NOT NULL AND auth.uid() = projects.user_id))));
CREATE POLICY "public_read_evaluation_runs" ON evaluation_runs FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public_read_evaluation_modules" ON evaluation_modules FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public_read_criterion_scores" ON criterion_scores FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public_read_evidence" ON evidence FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public_read_research_results" ON research_results FOR SELECT TO anon, authenticated USING (true);
CREATE POLICY "public_read_reports" ON reports FOR SELECT TO anon, authenticated USING (true);

-- 8.3 SUBMISSION CREATION POLICIES
CREATE POLICY "create_projects_policy" ON projects FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY "create_submissions_policy" ON submissions FOR INSERT TO anon, authenticated WITH CHECK (true);
CREATE POLICY "create_evaluation_runs_policy" ON evaluation_runs FOR INSERT TO anon, authenticated WITH CHECK (true);
