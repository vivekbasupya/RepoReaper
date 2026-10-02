# RepoReaper

Hunt the bug. Prove the fix.

Python/React implementation of the authoritative [specification](requirement.md).
This is a working curated fixture slice; later product milestones remain in progress.
See [progress](docs/progress.md), [gate evidence](docs/architecture/gate-report.md),
[stability policy](docs/architecture/stability-plan.md) and [local threat model](docs/threat-model/local.md).

## Reproducible local setup

Requires a Linux Docker engine (Docker Desktop/WSL2 on Windows), Python 3.12, uv 0.12.22,
Node 22.20 and pnpm 11.19.0. Dependencies are frozen in `uv.lock`,
`apps/web/pnpm-lock.yaml` and the trusted TypeScript profile's `package-lock.json`.
No paid model credentials are needed. Publication is disabled.

On Windows select the Linux engine: `docker context use desktop-linux`.
From the repository root:

```powershell
uv sync --frozen
uv run python scripts/init_env.py
docker build -f infra/containers/python.Dockerfile -t reporeaper-python:local .
docker build -f infra/containers/node.Dockerfile -t reporeaper-node:local .
uv run python scripts/pin_profiles.py
docker compose --profile runner build api runner web
docker compose up -d postgres redis qdrant
docker compose run --rm migrate
docker compose --profile runner up -d api graph dispatcher runner runner-worker web
```

Open [the local app](http://localhost:8080). Only the web proxy binds to loopback;
database, queue, vector service and runner have no public ports. The local session uses
workspace membership checks. Hosted authentication is a later milestone.

Fixtures/evaluators are baked into immutable profile images. Rebuild profiles, pin digests,
then recreate services after fixture/compiler changes. Accepted runs retain captured
configuration; never change their image identities silently. Schema migration and
LangGraph checkpoint-table setup are explicit deployment steps.

## Real architecture gate

The gate deliberately kills trusted test processes and recreates **only** the named local
Redis container. PostgreSQL and artifact volumes are retained. Use an isolated local deployment;
the one-shot fault probes and daemon access belong to the trusted gate controller.

```powershell
docker compose -f compose.yaml -f compose.gate.yaml --profile runner up -d api graph dispatcher runner runner-worker web
docker compose -f compose.yaml -f compose.gate.yaml --profile test run --rm gate
```

Run the gate after migrations/seed. Select services explicitly so the test container cannot
race migration/startup. Reports are written to `docs/architecture/reports`.
No mocked/skipped gate is a pass. Restore normal services to disable fault probes afterward:

```powershell
docker compose --profile runner up -d api graph dispatcher runner runner-worker web
```

## Other checks

```powershell
uv run ruff check .
uv run pytest tests/unit -q
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web build
pnpm --dir apps/web exec playwright install chromium --only-shell
pnpm --dir apps/web exec playwright test
```

Browser tests use real API state and execute fixture runs. Chromium needs system
dependencies on Linux (`playwright install --with-deps`). GitHub Actions reproduces
frozen builds, the real gate and browser checks; CI itself is unverified until the workflow
runs on GitHub. No remote push is required for local verification.

## Recovery and limitations

Redis is delivery only. Dispatcher requeues incomplete PostgreSQL commands. Restart
graph/controller processes without deleting data. Never use `down -v` on data to retain.
Follow the stability policy for backups, populated migrations and old graph executables.

The deterministic model repairs a known boundary fixture. Qdrant fixture vectors are
nonsemantic; mixed React execution is deliberately missing in M0 and yields partial
verification. Generic ingestion, full approvals, GitHub integration and the benchmark corpus
remain later work. The curated Docker controller is not a public untrusted-code sandbox.
Its daemon socket is never mounted into API, graph or repository containers.
Generated credentials live only in ignored `.env`; the sample database password
is for local development.
