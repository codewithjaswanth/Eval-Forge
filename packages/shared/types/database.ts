// ==============================================================================
// EvalForge: Supabase Database Types (Generated TypeScript Strict Mode)
// ==============================================================================

export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type RunStatus = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ModuleStatus = 'pending' | 'running' | 'completed' | 'skipped' | 'failed';
export type SubmissionStatus = 'pending' | 'processing' | 'processed' | 'failed';
export type EvidenceType =
  | 'deterministic_tool'
  | 'static_ast'
  | 'llm_reasoning'
  | 'web_citation'
  | 'performance_metric'
  | 'security_finding'
  | 'manual_override'
  | 'unmeasurable';

export interface Database {
  public: {
    Tables: {
      scoring_rubrics: {
        Row: {
          version: string;
          name: string;
          description: string | null;
          total_weight: number;
          is_active: boolean;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          version: string;
          name: string;
          description?: string | null;
          total_weight?: number;
          is_active?: boolean;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          version?: string;
          name?: string;
          description?: string | null;
          total_weight?: number;
          is_active?: boolean;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
      rubric_categories: {
        Row: {
          id: string;
          rubric_version: string;
          category_key: string;
          name: string;
          description: string | null;
          weight: number;
          evaluator_name: string;
          criteria_rubric: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          rubric_version: string;
          category_key: string;
          name: string;
          description?: string | null;
          weight: number;
          evaluator_name: string;
          criteria_rubric?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          rubric_version?: string;
          category_key?: string;
          name?: string;
          description?: string | null;
          weight?: number;
          evaluator_name?: string;
          criteria_rubric?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
      projects: {
        Row: {
          id: string;
          user_id: string | null;
          name: string;
          repo_url: string;
          live_url: string | null;
          description: string | null;
          is_public: boolean;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          user_id?: string | null;
          name: string;
          repo_url: string;
          live_url?: string | null;
          description?: string | null;
          is_public?: boolean;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          user_id?: string | null;
          name?: string;
          repo_url?: string;
          live_url?: string | null;
          description?: string | null;
          is_public?: boolean;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
      submissions: {
        Row: {
          id: string;
          project_id: string;
          commit_hash: string | null;
          branch: string;
          status: SubmissionStatus;
          metadata: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          project_id: string;
          commit_hash?: string | null;
          branch?: string;
          status?: SubmissionStatus;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          project_id?: string;
          commit_hash?: string | null;
          branch?: string;
          status?: SubmissionStatus;
          metadata?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
      evaluation_runs: {
        Row: {
          id: string;
          submission_id: string;
          rubric_version: string;
          status: RunStatus;
          overall_score: number | null;
          confidence_score: number | null;
          error_information: Json | null;
          worker_id: string | null;
          started_at: string | null;
          completed_at: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          submission_id: string;
          rubric_version?: string;
          status?: RunStatus;
          overall_score?: number | null;
          confidence_score?: number | null;
          error_information?: Json | null;
          worker_id?: string | null;
          started_at?: string | null;
          completed_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          submission_id?: string;
          rubric_version?: string;
          status?: RunStatus;
          overall_score?: number | null;
          confidence_score?: number | null;
          error_information?: Json | null;
          worker_id?: string | null;
          started_at?: string | null;
          completed_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
      };
      evaluation_modules: {
        Row: {
          id: string;
          run_id: string;
          module_name: string;
          status: ModuleStatus;
          score: number | null;
          max_score: number | null;
          confidence: number | null;
          error_information: Json | null;
          started_at: string | null;
          completed_at: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          run_id: string;
          module_name: string;
          status?: ModuleStatus;
          score?: number | null;
          max_score?: number | null;
          confidence?: number | null;
          error_information?: Json | null;
          started_at?: string | null;
          completed_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          run_id?: string;
          module_name?: string;
          status?: ModuleStatus;
          score?: number | null;
          max_score?: number | null;
          confidence?: number | null;
          error_information?: Json | null;
          started_at?: string | null;
          completed_at?: string | null;
          created_at?: string;
          updated_at?: string;
        };
      };
      criterion_scores: {
        Row: {
          id: string;
          run_id: string;
          module_id: string | null;
          category_key: string;
          criterion: string;
          score: number;
          max_score: number;
          weight: number;
          confidence: number;
          summary: string;
          strengths: Json;
          weaknesses: Json;
          recommendations: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          run_id: string;
          module_id?: string | null;
          category_key: string;
          criterion: string;
          score: number;
          max_score: number;
          weight: number;
          confidence?: number;
          summary: string;
          strengths?: Json;
          weaknesses?: Json;
          recommendations?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          run_id?: string;
          module_id?: string | null;
          category_key?: string;
          criterion?: string;
          score?: number;
          max_score?: number;
          weight?: number;
          confidence?: number;
          summary?: string;
          strengths?: Json;
          weaknesses?: Json;
          recommendations?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
      evidence: {
        Row: {
          id: string;
          run_id: string;
          criterion_score_id: string | null;
          evidence_type: EvidenceType;
          source: string;
          metric: string;
          value: Json;
          interpretation: string;
          raw_data: Json;
          citation_reference: Json | null;
          timestamp: string;
          created_at: string;
        };
        Insert: {
          id?: string;
          run_id: string;
          criterion_score_id?: string | null;
          evidence_type: EvidenceType;
          source: string;
          metric: string;
          value: Json;
          interpretation: string;
          raw_data?: Json;
          citation_reference?: Json | null;
          timestamp?: string;
          created_at?: string;
        };
        Update: {
          id?: string;
          run_id?: string;
          criterion_score_id?: string | null;
          evidence_type?: EvidenceType;
          source?: string;
          metric?: string;
          value?: Json;
          interpretation?: string;
          raw_data?: Json;
          citation_reference?: Json | null;
          timestamp?: string;
          created_at?: string;
        };
      };
      research_results: {
        Row: {
          id: string;
          run_id: string;
          query: string;
          title: string;
          url: string;
          source: string;
          similarity_assessment: string;
          relevance: number | null;
          summary: string;
          raw_metadata: Json;
          created_at: string;
        };
        Insert: {
          id?: string;
          run_id: string;
          query: string;
          title: string;
          url: string;
          source: string;
          similarity_assessment: string;
          relevance?: number | null;
          summary: string;
          raw_metadata?: Json;
          created_at?: string;
        };
        Update: {
          id?: string;
          run_id?: string;
          query?: string;
          title?: string;
          url?: string;
          source?: string;
          similarity_assessment?: string;
          relevance?: number | null;
          summary?: string;
          raw_metadata?: Json;
          created_at?: string;
        };
      };
      reports: {
        Row: {
          id: string;
          run_id: string;
          project_id: string;
          overall_score: number;
          rubric_version: string;
          weights_snapshot: Json;
          score_breakdown: Json;
          executive_summary: string;
          key_strengths: Json;
          key_weaknesses: Json;
          action_plan: Json;
          similar_projects: Json;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          run_id: string;
          project_id: string;
          overall_score: number;
          rubric_version: string;
          weights_snapshot: Json;
          score_breakdown: Json;
          executive_summary: string;
          key_strengths?: Json;
          key_weaknesses?: Json;
          action_plan?: Json;
          similar_projects?: Json;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          id?: string;
          run_id?: string;
          project_id?: string;
          overall_score?: number;
          rubric_version?: string;
          weights_snapshot?: Json;
          score_breakdown?: Json;
          executive_summary?: string;
          key_strengths?: Json;
          key_weaknesses?: Json;
          action_plan?: Json;
          similar_projects?: Json;
          created_at?: string;
          updated_at?: string;
        };
      };
    };
    Functions: {
      claim_next_evaluation_run: {
        Args: { p_worker_id: string };
        Returns: Database['public']['Tables']['evaluation_runs']['Row'][];
      };
    };
  };
}
