# Deployment guide — EquiTask AI

> **DRAFT — requires security review before real users.**
>
> This document describes deployment infrastructure for a research prototype
> (v0.1.0). It is NOT a production readiness statement. Do not expose this
> service to real users or real personal data until a security review,
> penetration test, and operational review have been completed.

## 1. Deployment options

| Option | When to use | Status |
|--------|-------------|--------|
| `docker compose` (backend/docker-compose.yml) | Local development, demos, CI smoke tests | Implemented |
| Docker image (`backend/Dockerfile`) | Any OCI-compliant runtime (Nomad, ECS, Cloud Run, Kubernetes) | Implemented (unhardened) |
| GitHub Actions CD (.github/workflows/deploy.yml) | Build + container scan on push to master; staging deploy placeholder; production gated behind manual approval | Implemented (placeholders) |
| Bare-metal / venv | Development only | Supported |

There is no Kubernetes Helm chart, no Terraform, no managed service integration, and no blue/green or canary rollout mechanism yet.

## 2. Local development with Docker Compose

```powershell
# 1. Copy the example environment file (never commit .env)
cd backend
copy .env.example .env   # PowerShell: Copy-Item .env.example .env
# 2. Edit .env if you want non-default values, then start the stack
docker compose up --build
```

What happens:

- `db` — PostgreSQL 16, data persisted in the `equitask_db_data` named volume.
- `migrate` — runs `alembic upgrade head` against PostgreSQL and exits (`restart: "no"`).
- `app` — FastAPI backend on `http://localhost:8000`; API docs at `/docs`; enhanced health probe at `/health`.
- The app starts only after migrations complete and the DB is ready.

Useful commands:

```powershell
docker compose up -d                # start in background
docker compose logs -f app          # follow backend logs
docker compose exec app alembic current   # show applied migration
docker compose exec app alembic upgrade head   # apply pending migrations
docker compose down -v              # stop and remove DB volume (data loss!)
```

Demo seeding is disabled by default (`EQUITASK_ENABLE_DEMO_SEED=false`). To seed a throwaway dev database:

```powershell
# set EQUITASK_ENABLE_DEMO_SEED=true in .env, then:
docker compose up --build
curl -X POST http://localhost:8000/api/v1/demo/seed -H "Content-Type: application/json" -d '{"tasks":6,"volunteers":8,"seed":42}'
```

Never enable demo seeding on a database that holds real data.

## 3. Building and running the container image directly

```powershell
docker build -t equitask-backend:local -f backend/Dockerfile backend
docker run --rm -p 8000:8000 \
  -e EQUITASK_DATABASE_URL="sqlite:///./equitask.db" \
  -e EQUITASK_SECRET_KEY="<generate-a-32-byte-secret>" \
  equitask-backend:local
```

The image runs as non-root user `equitask` and defines a `HEALTHCHECK`
against `http://localhost:8000/health`. Orchestrators should fail the
container when that probe returns non-200.

## 4. Environment variables

All settings are read with the `EQUITASK_` prefix (Pydantic Settings, see
`backend/app/config.py`).

| Variable | Example | Notes |
|----------|---------|-------|
| `EQUITASK_DATABASE_URL` | `sqlite:///./equitask.db` | SQLite (dev default) or `postgresql+psycopg2://user:pass@host:5432/db` |
| `EQUITASK_SECRET_KEY` | `<32+ random chars>` | JWT signing secret. **Change before any real deployment.** |
| `EQUITASK_TOKEN_TTL_MINUTES` | `720` | Access token lifetime |
| `EQUITASK_PASSWORD_ITERATIONS` | `210000` | PBKDF2 iterations |
| `EQUITASK_SOLVER_TIME_LIMIT_SECONDS` | `5` | OR-Tools CP-SAT time limit per run |
| `EQUITASK_MAX_PROBLEM_VOLUNTEERS` | `200` | Problem size guardrail |
| `EQUITASK_MAX_PROBLEM_TASKS` | `200` | Problem size guardrail |
| `EQUITASK_REQUEST_RATE_LIMIT` | `120` | Per-client requests per window (in-process) |
| `EQUITASK_STALE_FIELD_HOURS` | `336` | Stale-data threshold |
| `EQUITASK_ENABLE_DEMO_SEED` | `false` | Enable only on throwaway dev/staging DBs |
| `EQUITASK_LOG_LEVEL` | `INFO` | Application log level |

Generate secrets with `python -c "import secrets; print(secrets.token_urlsafe(32))"`.

## 5. Database migrations

Migrations are managed with Alembic (`backend/alembic/`).

```powershell
# Apply pending migrations (production deployments should run this BEFORE
# starting/restarting the app):
alembic upgrade head

# Check which revision is applied:
alembic current

# Show pending migrations:
alembic heads
```

The `/health` endpoint reports migration status (`current`, `behind`,
`not_applicable`, `error`). A `behind` status means the code expects a
schema the database does not have yet — run `alembic upgrade head`.

There are no tested downgrade paths; plan rollbacks by re-deploying the
previous image rather than downgrading the schema (see docs/OPERATIONS.md).

## 6. Backup and restore

PostgreSQL (Docker Compose):

```powershell
# Backup
docker compose exec db pg_dump -U equitask -d equitask > backup_$(Get-Date -Format "yyyyMMdd_HHmmss").sql

# Restore (into a freshly started db service)
docker compose exec -T db psql -U equitask -d equitask < backup_file.sql
```

SQLite (dev):

```powershell
copy backend\equitask.db backup\equitask-$(Get-Date -Format "yyyyMMdd").db
```

Backup strategy (draft): daily automated pg_dump, weekly full volume snapshot,
retain backups for 30 days, store off-site or in a different account/region,
and **test restores quarterly**. A backup is not a backup until a restore has
been proven to work.

## 7. Monitoring

- Health probe: `GET /health` returns `{status, service, version, database_url_kind, checks:{database,solver,migrations}}`.
- Use the probe for load balancer / container readiness and liveness.
- Logs go to stdout/stderr; ship them to your log aggregator. No structured
  logging or request IDs are implemented yet.
- There are no built-in Prometheus metrics. Add a metrics middleware or a
  Prometheus exporter sidecar before production.

Alert on: `status == "degraded"`, any check `== "error"`, repeated probe
failures, solver timeouts (5xx on `/api/v1/allocations/run`).

## 8. Secrets management

- Never commit `backend/.env` or real values of `EQUITASK_SECRET_KEY`,
  database passwords, or demo credentials to git.
- In CI/CD, use repository/environment secrets (GitHub Actions secrets) and
  pass them into the container at runtime; do not bake them into the image.
- For production, use a secrets manager (e.g. AWS Secrets Manager, HashiCorp
  Vault) and inject secrets as environment variables or mounted files at
  container startup.
- Rotate `EQUITASK_SECRET_KEY` on a schedule and immediately after any
  suspected leak. Rotation invalidates all outstanding tokens.

## 9. SSL/TLS and transport security

- Terminate TLS at a reverse proxy / ingress (nginx, Traefik, Cloudflare,
  AWS ALB) using certificates from a public CA (e.g. Let's Encrypt via
  cert-manager).
- Enforce HSTS and secure, `SameSite` cookies once session cookie handling
  is hardened.
- Do not terminate TLS inside the FastAPI container for production traffic.

## 10. Rate limiting

The app ships a small in-process fixed-window limiter
(`backend/app/main.py`, `SimpleRateLimit`). It is **per-process**: behind a
load balancer with multiple instances the effective limit is
`limit × instances`. For production, enforce rate limiting at the gateway
(e.g. nginx `limit_req`, Cloudflare, or an API gateway) and treat the
in-process limiter as defense in depth.

## 11. Known limitations (not production ready)

- No authentication middleware beyond JWT tokens; no refresh-token rotation,
  no MFA, no account lockout.
- In-process rate limiter and in-memory state do not scale across instances.
- No distributed tracing, structured logging, or Prometheus metrics.
- No blue/green, canary, or zero-downtime deployment mechanism.
- Demo credentials are hardcoded in `backend/app/api.py` and only gated by
  `EQUITASK_ENABLE_DEMO_SEED=false`.
- OR-Tools CP-SAT runs single-threaded (`num_search_workers = 1`) for
  determinism; CPU-bound solver work can block the event loop.

Treat every item above as required work before declaring production readiness.
