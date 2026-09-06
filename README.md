# EvalForge

> **Automated, deterministic, and empirical engineering evaluation platform for software projects.**

EvalForge inspects submitted repositories, analyzes architecture, runs deterministic code quality and static tools, measures live website performance and accessibility via Playwright, assesses innovation against existing open-source projects, and synthesizes an immutable, reproducible evaluation report scored out of 100.

---

## Key Capabilities

- **Deterministic Code Quality**: Integrates real static analyzers (ESLint, Prettier, TypeScript, flake8, pytest) without relying on LLM guesswork.
- **Empirical Live Website Auditing**: Headless Playwright tests for desktop & mobile viewports, WCAG accessibility violations, DOM interactive elements, layout stability, and network errors with strict SSRF guards.
- **Qualitative Grounded Evaluation**: Problem and Solution analyzers evaluate architecture and feasibility against explicit rubrics with mandatory repository file citations.
- **Novelty & Prior-Art Research**: Generates targeted search queries to discover candidate projects, compares semantic similarities, detects differentiators, and rejects unsubstantiated novelty claims.
- **Deterministic Score Aggregator**: Scored against immutable Rubric v1.0.0 (10 criteria strictly summing to 100.00). Category scores cannot be overridden by LLMs.
- **Production-Hardened Security**: Containerized sandbox boundary (`10001:10001`, `--cap-drop=ALL`, CPU/memory/pid limits), safe git execution, path traversal guards, secret scrubbing, and SSRF route interception.
- **Reliable Queue Engine**: Atomic `FOR UPDATE SKIP LOCKED` claiming, automatic stale lease recovery, worker crash tolerance, and failure cascade skipping.

---

## Quickstart & Local Development

### Prerequisites
- Node.js 20+ and npm
- Python 3.11+
- Chromium for Playwright (`playwright install chromium`)
- Docker or Podman (optional, for isolated sandbox execution)

### 1. Web Application (`apps/web`)
```bash
cd apps/web
cp .env.example .env.local
npm install
npm run dev
```
Open [http://localhost:3000](http://localhost:3000) to access the dashboard and submission interface.

### 2. Evaluation Worker (`services/worker`)
```bash
cd services/worker
cp .env.example .env
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium
python -m analyzer.runner
```

---

## Running the Automated Test Suite

### Python Worker Tests (62 tests)
```bash
cd services/worker
.\.venv\Scripts\python -m pytest -v
```
Verifies:
- End-to-end evaluation flow with controlled multi-tier repository
- Playwright headless browser auditing & unmeasurable states
- Deterministic code quality scoring & penalty logic
- SSRF defenses (cloud metadata, loopbacks, RFC1918, octal/hex IPs)
- Subprocess secret scrubbing & git option injection prevention
- Queue atomic claiming, crash recovery, and stale lease reclamation
- ScoreAggregator 100.00-point total, immutability, and reproducibility

### Frontend TypeScript & Build Tests
```bash
cd apps/web
npm run lint
npm run build
```

---

## Documentation Links

- [Production Deployment Guide](file:///c:/Users/Jaswanth/Downloads/Projects/EvalForge/docs/DEPLOYMENT.md)
- [Worker Fleet Setup & Sandbox Hardening](file:///c:/Users/Jaswanth/Downloads/Projects/EvalForge/docs/WORKER_SETUP.md)
- [Supabase Database Migrations](file:///c:/Users/Jaswanth/Downloads/Projects/EvalForge/docs/MIGRATIONS.md)
