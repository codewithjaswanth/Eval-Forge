import { createClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseKey);

export const supabase: any = isSupabaseConfigured
  ? createClient(supabaseUrl!, supabaseKey!)
  : null;

// Fallback in-memory store for local testing without cloud Supabase connection
class LocalMemoryStore {
  private static instance: LocalMemoryStore;
  public projects: Map<string, any> = new Map();
  public submissions: Map<string, any> = new Map();
  public evaluationRuns: Map<string, any> = new Map();
  public evaluationModules: Map<string, any> = new Map();
  public criterionScores: Map<string, any> = new Map();
  public evidence: Map<string, any[]> = new Map();
  public reports: Map<string, any> = new Map();

  private constructor() {}

  public static getInstance(): LocalMemoryStore {
    if (!LocalMemoryStore.instance) {
      LocalMemoryStore.instance = new LocalMemoryStore();
    }
    return LocalMemoryStore.instance;
  }
}

export const localStore = LocalMemoryStore.getInstance();
