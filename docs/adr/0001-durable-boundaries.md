# ADR 0001 — authoritative intent and checkpoint handoff

Accepted for M0. Section 21 resolves earlier graph shorthand: an interrupted graph alone is
not an execution transaction. PostgreSQL product state is authoritative; every tool has a
run/step/attempt-derived UUID and input hash. The exact wait checkpoint makes it dispatchable.
Transport retries preserve identities. Receipts expire; published_at is never completion.

Graph ownership combines a PostgreSQL session advisory lock (protecting saver calls) with
expiring leases and fenced product writes. Async clients are created after Celery prefork
inside one asyncio.run per task and closed before return. Human/sandbox waits release slots.
SQL transactions never span network calls. Reconciler leadership and runner reservations are
shared SQL state. No process-local semaphore is an authoritative global limit.

Typed adapters isolate Docker, Qdrant, filesystem artifacts and deterministic models. Curated
Docker execution is local-only, no app secrets/socket/mounts are passed into the sandbox.
The dedicated runner controller itself needs privileged daemon access and is a trusted boundary.
Public untrusted execution requires a stronger provider/VM and separate host.

M0's model and 8-dimensional hash embedding are explicitly fixture adapters, not production
coding/semantic models. This avoids paid calls while proving real persistence and execution.
Mixed fixture deliberately keeps React unverified to test honest outcome aggregation.
