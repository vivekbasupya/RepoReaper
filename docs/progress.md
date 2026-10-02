# RepoReaper implementation progress

Specification: `requirement.md` v1.2, read in full before implementation.
Workspace initially empty; no applicable AGENTS.md. Public project-source publication to
vivekbasupya/RepoReaper authorized on 2026-10-03. Application-created PRs and deployments
remain disabled. The owner requested no license yet.

## Architecture and decisions

Python 3.12 API; React/TypeScript frontend; PostgreSQL authoritative state; Redis/Celery
prefork delivery; LangGraph PostgreSQL checkpoints; private runner controlling hardened
disposable Python/Node containers; Qdrant derived, workspace-filtered fixture index.
Section 21's checkpoint-before-dispatch rule takes precedence over shorthand earlier flows.
The attached Downloads/RepoReaper file is a specification file, not a checkout; implementation
lives in this workspace and its full contents are preserved as requirement.md.

No blocking product choices. Docker Desktop must be running. Paid credentials are unnecessary
for M0. Docker socket belongs only to the runner controller and trusted test-control plane.
This local curated mode is unsuitable for public untrusted repository execution.

## Milestone checklist and acceptance criteria

- [x] **M0 — mandatory gate:** compatible locked packages; all six syntax adapters; real
  PostgreSQL checkpoint/interrupt/resume; real filtered Qdrant query; real Python and Node
  baseline/patched harness; minimal React diff; **all ten section 21 gate scenarios pass**
  with recorded process topology, evidence and resource measurements.
- [ ] **M1 — shell and jobs:** two independent fixture runs create, reconnect, cancel and
  retry with persisted truthful state and complete UI loading/error/empty states.
- [ ] **M2 — ingestion/retrieval:** bounded Tree-sitter chunks, manifests, generic fallback,
  dense/sparse/exact fusion, generation recovery, correct SHA citations, no tenant leakage.
- [ ] **M3 — reproduction:** Python and TypeScript failing cases; deadlines/cancellation,
  sandbox cleanup and raw evidence. Go/JVM profiles before R2.
- [ ] **M4 — verification:** actual Python, TypeScript and mixed React defects verified by
  immutable evaluator tests; all affected targets covered; review and export.
- [ ] **M5 — approval/GitHub:** exact-artifact approval, scoped App integration, idempotent
  authorized draft PR, stale/replayed approval tests. Activation requires user authorization.
- [ ] **M6 — reliability/evaluation:** concurrency/security/upgrade checks, frozen held-out
  corpus, actual per-language metrics, responsive/accessibility/visual inspection and guides.

## Implemented within the M0 slice

- Versioned run, execution, result and error DTOs; typed provider interfaces.
- Explicit Alembic migration with workspace-scoped foreign keys, run leases/fencing,
  commands/receipts/intents, reservations, events and runner persistence.
- Stable operation identities and checkpoint/dispatch reconciliation; graph workers release waits.
- Scoped fixture snapshots with Git object-derived commit SHAs; baseline language parser registry.
- Async runner API and durable polling; shared PostgreSQL capacity; network-free non-root
  containers with readonly root, tmpfs quotas, memory/PID/CPU/log/time limits.
- Deterministic fixture patch, external immutable evaluator, observed baseline and patched results.
- API-based React screen; Radix/shadcn-style owned button, Tailwind, Motion, lazy Monaco
  and React Flow; SSE replay, cancellation, source citations, partial coverage and export.
- Frozen uv/pnpm locks and trusted TypeScript compiler npm lock; installed and built.

## Checks and continuation

M0 accepted on 2026-10-03 IST: **17 real architecture tests passed** in 219.89s, no mocks,
failures or skips; 9 unit checks passed; Ruff and mypy (domain/config/languages) passed.
Two real Playwright tests passed; desktop/mobile evidence and Monaco diff were inspected.
See `architecture/gate-report.md` for exact scenario mapping, resource limits, observed
measurements, reproduced failures and scope. API metadata p95 was 33.12ms over 20 samples;
two runner controllers respected one shared slot. The initial GitHub Actions workflow passed
in run 37052607733; later commits require their own CI evidence.

Publication audit on 2026-10-03: full two-commit history scanned by Gitleaks 8.30.1, no
leaks found. Two actual generated local credentials were absent from all 101 historical
blobs; local dependencies/data remained excluded. Expanded Git/Docker environment-variant,
key, editor and transient-data exclusions; 18 Git ignore probes passed. Added a full-history
CI secret scan. Docker context verified nine local-file exclusions with template/source retained.

Next: M1 linked retry with explicit configuration and idempotency; replay/reconnect persistence,
cancel transition tests, truthful metadata, loading/error/disconnected states. Preserve the
accepted M0 gate before changing boundaries; rerun meaningful real integration checks.
After M1 acceptance, proceed to M2 ingestion/retrieval without relabeling fixture hashes semantic.

Current known limitations: fixture-only repositories and deterministic patching; nonsemantic
fixture embeddings (no production retrieval claim); mixed React target intentionally lacks a
runtime profile; hosted auth, full approval/publication, arbitrary patch ingestion, generation
management, complete resource metrics and later milestones remain unimplemented.
