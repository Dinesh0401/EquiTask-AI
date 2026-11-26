# Operations runbook — EquiTask AI

> **DRAFT — requires security review before real users.**
>
> This runbook accompanies a research prototype (v0.1.0). It is NOT a
> production readiness statement. Procedures here are placeholders where no
> real infrastructure is wired.

## 1. Health checks

Endpoint: `GET /health` (also `GET /api/v1/health`)

Example healthy response:

```json
{
  "status": "ok",
  "service": "equitask",
  "version": "0.1.0",
  "database_url_kind": "postgresql",
  "checks": {
    "database": { "status": "ok" },
    "solver": { "status": "ok", "engine": "ortools-cpsat", "search_workers": 1 },
    "migrations": { "status": "current", "current": "8bd875fb2030", "heads": ["8bd875fb2030"] }
  }
}
```

Checks:

| Check | Healthy | Unhealthy | Action |
|-------|---------|-----------|--------|
| `database` | `status: "ok"` (`select 1` succeeds) | `error` | Verify the database is reachable, credentials in `EQUITASK_DATABASE_URL` are correct, and the server is not overloaded. |
| `solver` | `status: "ok"` (OR-Tools CP-SAT instantiable) | `error` | The container image may be missing the ortools dependency; redeploy the image. |
| `migrations` | `current` / `not_applicable` | `behind` / `error` / `empty` | Run `alembic upgrade head`; if the error persists, inspect migration scripts and database schema drift. |

HTTP status: 200 whenever the app process can answer. Orchestrators should
treat non-200 as unhealthy. Monitor the `status` field: `degraded` means at
least one check failed.

Container health check (Docker): `curl -fsS http://localhost:8000/health`
every 30s, 3 retries before marking unhealthy.

## 2. Logs

- Application logs write to stdout/stderr; Docker Compose captures them via
  `docker compose logs [--follow] app`.
- Log level is controlled by `EQUITASK_LOG_LEVEL` (default `INFO`).
- No structured (JSON) logging, no correlation/request IDs, and no log
  rotation are implemented yet — configure the container driver's log
  rotation (e.g. `max-size`, `max-file`) to prevent disk fill.

## 3. Metrics

There are no built-in Prometheus metrics or endpoints. Before production,
add:

- Request rate, error rate, and latency (RED metrics) via middleware or a
  gateway exporter.
- Solver runtime and status (already recorded in `allocation_runs` — can be
  queried from the database).
- Health probe status exported as a metric for alerting.

## 4. Incident response

### P1 — Health probe failing / service unreachable

1. Check `docker compose ps` (or orchestration equivalent): is the `app`
   container running or restarting?
2. `docker compose logs app` — look for tracebacks, port conflicts, OOM
   kills.
3. `curl http://localhost:8000/health` — which check is failing?
4. If DB is down: check `db` container and `pg_isready`; verify the
   `equitask_db_data` volume is mounted.
5. Roll forward: redeploy the last known-good image tag (see §6).

### P2 — `migrations` check is `behind` or `error`

1. Do not force writes while schema state is unknown.
2. Run `alembic current` and `alembic heads`.
3. If behind: `alembic upgrade head` during a maintenance window.
4. If error: stop deploys, inspect the migration that failed, and page the
   maintainer. Do not manually edit the `alembic_version` table.

### P3 — Solver timeouts or 500 on `/api/v1/allocations/run`

1. Confirm problem size is within `EQUITASK_MAX_PROBLEM_VOLUNTEERS` /
   `EQUITASK_MAX_PROBLEM_TASKS`.
2. Consider raising `EQUITASK_SOLVER_TIME_LIMIT_SECONDS` or reducing the
   problem scope; the solver is single-threaded and CPU-bound.
3. Check instance CPU saturation; scale out or add CPU limits.

### P4 — Suspected secret leak (e.g. `EQUITASK_SECRET_KEY` committed)

1. Rotate the secret immediately; invalidate all outstanding tokens.
2. Remove the secret from git history (this rewrites history — coordinate
   with all contributors).
3. Review access logs for unauthorized token use.

## 5. Rollback procedure

There are no tested database downgrades. Roll back by **rolling forward**:

1. Identify the last known-good image tag (e.g. from GHCR:
   `ghcr.io/<owner>/equitask-backend:<sha>`).
2. Redeploy that tag: `docker compose pull` / `docker compose up -d` (or
   equivalent in your orchestrator).
3. Verify `GET /health` returns `status: ok` and `migrations.status` is
   `current`.
4. Do NOT run `alembic downgrade` — downgrade paths beyond the initial
   migration are not exercised by tests.

If a bad migration was applied and the app cannot start, fix the migration,
bump it to a new head, and `alembic upgrade head` again.

## 6. Scaling considerations

- The FastAPI app is stateless; scale horizontally behind a load balancer.
- The in-process rate limiter is per-instance: effective limit =
  `EQUITASK_REQUEST_RATE_LIMIT × instances`. Enforce a shared limit at the
  gateway for production.
- JWT validation is stateless — no sticky sessions required.
- The CP-SAT solver is CPU-bound and single-threaded (`num_search_workers =
  1`). Concurrent allocation runs compete for CPU; consider a worker queue
  or concurrency cap under load.
- Database connections: tune the SQLAlchemy pool if you run many instances
  against one PostgreSQL (currently `create_engine` defaults).

## 7. Maintenance windows

1. Announce the window; stop traffic at the load balancer (drain).
2. Run `alembic upgrade head` while the app is stopped (zero-downtime
   migrations are not supported yet).
3. Deploy the new image.
4. Verify `GET /health`, then re-enable traffic.
5. Keep the previous image tag available until the new release is stable.

## 8. On-call and contacts

Placeholder: no on-call rotation or incident channel is configured.
Escalate to the repository maintainer for incidents during this prototype
phase.

## 9. Checklist before exposing to users

- [ ] Security review of this runbook and DEPLOYMENT.md completed
- [ ] Real secrets injected via a secrets manager (no `.env` committed)
- [ ] TLS terminated at ingress with a public CA certificate
- [ ] Gateway-level rate limiting enabled
- [ ] Structured logging and log rotation configured
- [ ] Prometheus metrics endpoint added and alerting configured
- [ ] Backup/restore tested end-to-end (pg_dump + restore)
- [ ] Rollback drill performed with a previous image tag
- [ ] Demo seeding disabled (`EQUITASK_ENABLE_DEMO_SEED=false`) on all
  production-adjacent data
