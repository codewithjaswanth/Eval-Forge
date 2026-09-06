# EvalForge Database Migrations & Supabase Instructions

This guide provides step-by-step instructions for provisioning, configuring, and verifying the PostgreSQL schema and Row Level Security (RLS) policies for EvalForge.

---

## 1. Migration File Inventory

All migration scripts are versioned and located in [`supabase/migrations/`](file:///c:/Users/Jaswanth/Downloads/Projects/EvalForge/supabase/migrations):

1. **`20260906000001_initial_schema.sql`**:
   - Creates core relational tables: `projects`, `submissions`, `evaluation_runs`, `evaluation_modules`, `criterion_scores`, `evidence`, `reports`, `citations`, `similar_projects`, and `audit_logs`.
   - Defines indexes on queue fields (`status`, `created_at`), run foreign keys, and unique constraints.
   - Configures Row Level Security (RLS) policies granting anonymous read access to public reports while restricting write operations exclusively to `service_role`.
   - Implements `claim_next_evaluation_run(p_worker_id text)` stored procedure using `FOR UPDATE SKIP LOCKED` for atomic queue processing.

2. **`20260906000002_scoring_rubric_seed.sql`**:
   - Creates `scoring_rubrics` and `rubric_criteria` tables with immutability triggers.
   - Seeds Rubric Version `1.0.0` with exactly 10 criteria totaling 100.00 points.
   - Enforces mathematical integrity constraint ensuring the sum of all criterion weights in any rubric version strictly equals 100.00.

---

## 2. Applying Migrations via Supabase CLI

If using the Supabase CLI with local development or remote linking:

```bash
# Link to your Supabase remote project
supabase link --project-ref <your-project-id>

# Apply pending migrations
supabase db push
```

---

## 3. Applying Migrations via Supabase Web Dashboard

If applying migrations manually through the Supabase Dashboard:

1. Open your project in the [Supabase Dashboard](https://supabase.com/dashboard).
2. Navigate to **SQL Editor**.
3. Create a **New Query**.
4. Paste the full contents of `supabase/migrations/20260906000001_initial_schema.sql` and click **Run**.
5. Create a second **New Query**.
6. Paste the full contents of `supabase/migrations/20260906000002_scoring_rubric_seed.sql` and click **Run**.

---

## 4. Verification Queries

Run the following SQL queries in the Supabase SQL Editor to verify that all tables, procedures, and constraints were created successfully:

### 1. Verify Core Tables
```sql
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;
```
*Expected tables:*
- `audit_logs`
- `citations`
- `criterion_scores`
- `evaluation_modules`
- `evaluation_runs`
- `evidence`
- `projects`
- `reports`
- `rubric_criteria`
- `scoring_rubrics`
- `similar_projects`
- `submissions`

### 2. Verify Atomic Queue Stored Procedure
```sql
SELECT routine_name, routine_type 
FROM information_schema.routines 
WHERE routine_schema = 'public' AND routine_name = 'claim_next_evaluation_run';
```
*Expected: 1 row returned (`FUNCTION`).*

### 3. Verify Rubric Weight Sums to Exact 100.00
```sql
SELECT 
    r.version,
    r.name,
    SUM(c.weight) AS total_weight,
    COUNT(c.id) AS criterion_count
FROM scoring_rubrics r
JOIN rubric_criteria c ON c.rubric_id = r.id
GROUP BY r.version, r.name;
```
*Expected Output:*
| version | name | total_weight | criterion_count |
| :--- | :--- | :--- | :--- |
| `1.0.0` | Production Engineering Rubric | `100.00` | `10` |

### 4. Verify Row Level Security (RLS) Status
```sql
SELECT 
    schemaname, 
    tablename, 
    rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public';
```
*Expected: `rowsecurity` is `true` for all public tables.*
