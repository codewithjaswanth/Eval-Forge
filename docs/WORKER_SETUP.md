# EvalForge Worker Fleet Setup & Sandbox Hardening

This guide details the operational configuration, security boundaries, and sandbox isolation architecture for EvalForge workers.

---

## 1. Sandbox Architecture & Isolation Strategy

EvalForge processes untrusted source repositories submitted by external users. To protect host infrastructure from malicious code, execution is split into two distinct tiers:

```
[Untrusted Repository Files]
          |
          v
+-----------------------------------------------------------+
| TIER 1: Static Inspection & Ingestion (Host Daemon)      |
|  - Strictly read-only file reading and AST parsing        |
|  - No repo scripts executed (no npm install, no setup.py) |
|  - Disposable workspace directory created per evaluation  |
|  - Environment sanitized (secrets stripped)              |
|  - Symlink validation prevents directory traversal        |
+-----------------------------------------------------------+
          |
          | (Dynamic Build / Execution Requested)
          v
+-----------------------------------------------------------+
| TIER 2: Isolated Container Sandbox (OCI Container)        |
|  - OCI Runtime: Docker or Podman                          |
|  - Non-root UID: 10001:10001                              |
|  - Read-only root filesystem (--read-only)                |
|  - Memory limit: 2048 MB (--memory=2048m)                 |
|  - CPU quota: 2 cores (--cpus=2.0)                        |
|  - PID limit: 100 processes (--pids-limit=100)            |
|  - Network disabled: (--network=none)                     |
|  - Capabilities dropped: (--cap-drop=ALL)                 |
|  - Execution timeout: 60 seconds                          |
|  - Host secrets completely excluded                       |
+-----------------------------------------------------------+
```

> [!IMPORTANT]
> The worker host daemon NEVER executes arbitrary repository build commands (e.g. `npm install`, `make`, `python setup.py`) directly on the host system. Dynamic execution commands MUST be dispatched via `IsolatedSandboxRunner`.

---

## 2. Sandbox Container Image Build

To prepare the isolated container image:

```dockerfile
# Dockerfile.sandbox
FROM alpine:3.19

# Create non-root user
RUN addgroup -g 10001 sandboxgroup && \
    adduser -u 10001 -G sandboxgroup -D -s /bin/sh sandboxuser

# Install minimal toolset
RUN apk add --no-cache bash nodejs npm python3

WORKDIR /workspace
USER 10001:10001

CMD ["/bin/sh"]
```

Build and tag the image on all worker nodes:
```bash
docker build -t evalforge-sandbox:latest -f Dockerfile.sandbox .
```

---

## 3. Worker Configuration & Environment Variables

Create `/etc/evalforge/worker.env` with restricted permissions (`chmod 600`):

```ini
# Supabase Connectivity
SUPABASE_URL=https://<your-project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>

# Worker Identity
WORKER_ID=worker-node-01

# Sandbox Configuration
CONTAINER_RUNTIME=docker
EVALFORGE_SANDBOX_IMAGE=evalforge-sandbox:latest

# LLM Provider Credentials
EVALFORGE_LLM_PROVIDER=gemini
EVALFORGE_LLM_MODEL=gemini-1.5-pro
GEMINI_API_KEY=<gemini-api-key>

# Research / Novelty Discovery
SEARCH_API_KEY=<search-engine-key>

# Logging
LOG_LEVEL=INFO
STRUCTURED_JSON_LOGGING=true
```

---

## 4. Systemd Service Unit

Create `/etc/systemd/system/evalforge-worker.service`:

```ini
[Unit]
Description=EvalForge Evaluation Worker Daemon
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=evalforge
Group=evalforge
WorkingDirectory=/opt/evalforge/services/worker
EnvironmentFile=/etc/evalforge/worker.env
ExecStart=/opt/evalforge/services/worker/.venv/bin/python -m analyzer.runner
Restart=always
RestartSec=5s
KillSignal=SIGTERM
TimeoutStopSec=30s

# Security sandboxing for the worker process itself
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/tmp /var/log/evalforge
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now evalforge-worker
```

---

## 5. Structured Logging & Observability

EvalForge emits structured JSON logs. Sensitive values (API keys, Supabase credentials, tokens) are scrubbed automatically before output:

```json
{
  "timestamp": "2026-09-06T12:45:00.123456Z",
  "level": "INFO",
  "logger": "evalforge.evaluator",
  "evaluation_run_id": "run-b52e3e57",
  "worker_id": "worker-node-01",
  "evaluator": "ui_ux",
  "duration_ms": 1420.5,
  "status": "completed",
  "message": "Evaluator ui_ux completed in 1420.5ms with score 14.50/15.00",
  "extra": {
    "score": 14.5,
    "confidence": 0.95
  }
}
```
