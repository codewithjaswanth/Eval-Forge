# EvalForge Production Deployment Guide

This document outlines the deployment process for EvalForge components in a production environment.

---

## 1. System Architecture Overview

EvalForge consists of three core components:

1. **Frontend & Ingestion API (`apps/web`)**: Next.js 16 (App Router + Turbopack) application providing repository submission, rate limiting, and the real-time engineering analysis dashboard.
2. **Evaluation Worker Fleet (`services/worker`)**: Python 3.11+ asynchronous workers that poll the queue using atomic `SKIP LOCKED` semantics, ingest repositories into disposable workspaces, and execute the 10-analyzer DAG.
3. **Database & Storage (`supabase`)**: PostgreSQL relational store with Row Level Security (RLS), ACID transactions, queue lease management, and Realtime pub/sub.

```
                  +-----------------------------------+
                  |      User Browser / Dashboard     |
                  +-----------------+-----------------+
                                    |
                          HTTPS / REST / WSS
                                    v
                  +-----------------------------------+
                  |        Next.js Frontend (Vercel)  |
                  |     - Zod Validation              |
                  |     - Sliding Window Rate Limit   |
                  |     - Anonymous Submission API    |
                  +-----------------+-----------------+
                                    |
                        Postgres RPC / REST (Service Role)
                                    v
+-----------------------------------------------------------------------+
|                       Supabase PostgreSQL                            |
|  - Table: projects, submissions, evaluation_runs (Queue)              |
|  - Table: evaluation_modules, criterion_scores, evidence, reports     |
|  - Function: claim_next_evaluation_run() [FOR UPDATE SKIP LOCKED]    |
+-----------------------------------+-----------------------------------+
                                    ^
                                    | Atomic Polling
                                    |
                  +-----------------+-----------------+
                  |      EvalForge Worker Daemon      |
                  |  - Disposable Workspace Isolation |
                  |  - Git Clone (safe_env, no hooks) |
                  |  - SSRF Route Interception        |
                  |  - Asynchronous DAG Pipeline      |
                  +--------+------------------+-------+
                           |                  |
                           v                  v
         +--------------------+    +--------------------+
         | Playwright Browser |    | OCI Container      |
         | Headless Audits    |    | Sandbox Runner     |
         +--------------------+    +--------------------+
```

---

## 2. Prerequisites & External Services

| Service | Minimum Tier | Purpose |
| :--- | :--- | :--- |
| **Supabase PostgreSQL** | Pro (or self-hosted) | ACID relational data, queue management, Realtime |
| **LLM Provider** | Gemini 1.5 Pro, Claude 3.5 Sonnet, or GPT-4o | Qualitative rubric analysis (Problem & Solution) |
| **Search Engine API** | Tavily Search, Serper, or Brave | Prior-art and novelty candidate retrieval |
| **Container Engine** | Docker 24+ or Podman 4+ | Sandboxed untrusted build & test execution |
| **Chromium Runtime** | Playwright with system libs | Live website DOM, responsive, and performance audits |

---

## 3. Database Setup & Migrations

Execute the migration scripts located in `supabase/migrations/` in sequence:

```bash
# 1. Apply schema and RLS policies
supabase db push
# or execute via psql:
psql $DATABASE_URL -f supabase/migrations/20260906000001_initial_schema.sql

# 2. Apply immutable scoring rubrics (v1.0.0)
psql $DATABASE_URL -f supabase/migrations/20260906000002_scoring_rubric_seed.sql
```

For detailed instructions and verification queries, consult [`docs/MIGRATIONS.md`](file:///c:/Users/Jaswanth/Downloads/Projects/EvalForge/docs/MIGRATIONS.md).

---

## 4. Frontend Web App Deployment (`apps/web`)

### Environment Variables
Configure the following in your hosting provider (e.g. Vercel, AWS Amplify, or Docker):

```ini
NEXT_PUBLIC_SUPABASE_URL=https://<your-project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<your-anon-public-key>
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-private-key>
NEXT_PUBLIC_APP_URL=https://evalforge.example.com
```

> [!CAUTION]
> Ensure `SUPABASE_SERVICE_ROLE_KEY` is NEVER prefixed with `NEXT_PUBLIC_`. It must remain strictly server-side.

### Build and Deploy
```bash
cd apps/web
npm install --frozen-lockfile
npm run build
npm run start
```

---

## 5. Worker Fleet Deployment (`services/worker`)

Each worker operates as an autonomous stateless daemon. Multiple workers can run horizontally without shared state; the database handles concurrency via atomic leasing.

### System Prerequisites
Workers require system packages for Chromium:
```bash
# On Debian/Ubuntu Linux
apt-get update && apt-get install -y \
    git \
    python3.11 \
    python3.11-venv \
    docker.io \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2
```

### Installation
```bash
cd services/worker
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Running the Worker Daemon
```bash
python -m analyzer.runner
```

For systemd service configuration and container sandboxing setup, refer to [`docs/WORKER_SETUP.md`](file:///c:/Users/Jaswanth/Downloads/Projects/EvalForge/docs/WORKER_SETUP.md).

---

## 6. Security & Hardening Checklist

- [x] **Subprocess Sanitization**: Parent environment secrets (API keys, Supabase credentials) are scrubbed before invoking `git` or CLI tools.
- [x] **Git Hook Prevention**: All git operations run with `-c core.hooksPath=/dev/null` to prevent malicious hook execution.
- [x] **Symlink Traversal Prevention**: `is_safe_path()` validates every traversed path against the sandbox root.
- [x] **SSRF Protection**: URL validation blocks IPv4/IPv6 loopbacks, RFC1918 ranges, CGNAT, cloud metadata endpoints (`169.254.169.254`), and octal/hex IP representations.
- [x] **Subresource Network Interception**: Playwright routes intercept all outgoing HTTP requests, aborting connections to internal network addresses.
- [x] **Deterministic Scoring**: Category weights strictly equal 100.00; missing evaluators are explicitly recorded as unmeasurable without awarding unearned points.
