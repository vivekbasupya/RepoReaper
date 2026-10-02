# ADR 0002 — pinned compatibility spike

Resolved and installed with Python 3.12.14 / uv 0.12.22 and pnpm 11.19.0.
Authoritative exact dependency trees are uv.lock and apps/web/pnpm-lock.yaml.

Actual Python integrations: FastAPI 0.142.2, SQLAlchemy 2.0.54, asyncpg 0.31.0,
Celery 5.6.3, LangGraph 1.2.12, checkpoint-postgres 3.1.2,
psycopg 3.3.6, Qdrant client 1.19.1 with server 1.19.0,
Tree-sitter 0.25.2 and independently compatible grammar versions.
Actual frontend: React 19.3.0, TypeScript 5.9.3, Vite 7.3.6,
Tailwind 4.3.3, Motion 12.43.0, Monaco 0.52.2, React Flow 12.12.0.
Retained Monaco 0.52 because wrapper 4.7 supports it; lazy load and self-host worker.
Pinned jest-dom 6.9.1 to avoid the incompatible/deprecated 6.10 release.

Official integration references checked during implementation:
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [Interrupt replay and Command resume](https://docs.langchain.com/oss/python/langgraph/interrupts)
- [Celery tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html)
- [SQLAlchemy loop/session ownership](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

Spike evidence is real service gate tests, not assumed API compatibility. LangGraph saver
creates its own tables in a dedicated schema; nodes before interrupts are durable-keyed.
Qdrant client/server minor versions aligned after resolution. Docker base images pin registry
digests. Built runtime digests are captured before accepting runs; old mutable-tag runs are
held with restart instructions. No coding/embedding provider purchase was made. Production
provider IDs remain a later explicitly configured benchmark decision.

Observed integration defects: Docker local log compression is invalid with max-file=1;
disable compression and classify Docker State.Error as environment_failure. Temporary API
replicas must receive the same pinned runtime configuration as the main API. These failures
were reproduced in executable gates before correction.
