# Local setup and recovery

## Docker engine or context unavailable

Start Docker Desktop and select its Linux engine. On Windows use
`docker context use desktop-linux`, then verify `docker info`.
Execution workers require Linux containers; the backend Python language and repository
target languages are independent. Start with roughly 4 GiB available to the engine.

## Image digest validation fails

Build both trusted runtime profiles, then run `uv run python scripts/pin_profiles.py`.
Use its `--context desktop-linux` option if the CLI's active context differs. Placeholder
values in `.env.example` are not executable image identities. Recreate application services
after updating deployment configuration; keep accepted runs' captured configuration intact.

## Missing database/checkpoint tables

Start PostgreSQL, Redis and Qdrant, then run `docker compose run --rm migrate`.
This applies Alembic and seeds fixture/checkpoint/index metadata. API startup does not
create schemas. Keep PostgreSQL volumes when recovering a populated deployment.

## Run stays queued or waits for execution

Check `docker compose --profile runner ps` and bounded logs for graph, dispatcher,
runner and runner-worker. Start the runner profile explicitly. Persisted commands recover
after Redis returns; do not delete PostgreSQL to repair delivery.

A waiting graph should have released its worker lease. A sandbox reservation stays occupied
until actual cleanup is confirmed. A daemon failure is not proof that a container is absent.
Unsupported old configuration should remain visible for restart/export, not be silently rewritten.

## Unexpected verification result

Inspect actual baseline and patched log artifacts, exit codes and hashes. An environment
failure or absent runtime profile is not a verified code fix. The current mixed React fixture
is intentionally partial. The form only investigates the curated boundary defect in M0.

## Browser test or editor problem

Install Chromium with `pnpm --dir apps/web exec playwright install chromium --only-shell`.
On Linux include `--with-deps`. Ensure the real web/API/worker/runner stack is ready at
`http://localhost:8080` before browser tests. Monaco is lazy-loaded with self-hosted workers;
the form and run state should appear before its larger bundle finishes loading.

## Safe stop and restart

Use `docker compose --profile runner stop` and `up -d` with explicit service names to resume.
Data remains in named PostgreSQL, Qdrant and artifact volumes. Avoid `down -v` when retaining
work. After architecture testing, recreate the normal services without `compose.gate.yaml`
to disable one-shot fault probes. Never point the destructive gate at a shared/production deployment.

## Information to include in a bug report

Commit, operating system/engine, fixture/language, exact steps, expected/observed state,
sanitized bounded logs, and whether the gate or UI reproduction is affected. Do not attach `.env`.
