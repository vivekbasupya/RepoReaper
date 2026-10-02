# Roadmap and acceptance criteria

M0 is accepted. R1 and R2 remain unfinished. Milestones proceed in order; existing boundary
tests stay executable as features are added.

| Milestone | State | Exit criteria |
|---|---|---|
| M0: architecture compatibility spike | Accepted | Ten real architecture scenarios; locked integrations; Python/TS execution; actual diff and persisted recovery evidence |
| M1: product shell and durable jobs | Next | Two independent fixture runs execute, reconnect, cancel and retry with truthful persisted state; complete UI states |
| M2: ingestion and retrieval | Planned | Authorized immutable snapshots, exclusions, bounded multi-language chunks/fallback, hybrid retrieval, generation recovery and SHA citations |
| M3: isolated reproduction | Planned; foundations in M0 | General Python/Node profiles, failing reproductions, limits, deadlines, raw artifacts and verified cleanup |
| M4: patching and verification | Planned; foundations in M0 | Controlled revisions and policy checks; real Python, TS and mixed React bugs fixed under unchanged evaluators |
| M5: approval and GitHub integration | Planned | Exact-artifact approvals, scoped App credentials, idempotent publication and recovery; live publication only when explicitly authorized |
| M6: reliability, evaluation and polish | Planned | Frozen held-out corpus, measured per-language quality, security/concurrency/upgrade checks, accessibility and operational guides |

**R1** requires usable Python and JavaScript/TypeScript workflows, mixed Python+React coverage,
review/export, cancel/retry and persistence. **R2** adds Go/JVM execution, GitHub App publication,
broader per-language evaluation and operational validation. Parsing Go or Java does not
complete their execution support. The current mixed partial result is a gate scenario,
not completion of R1's mixed verification requirement.

## Next implementation steps

1. Add a workspace-scoped linked retry with explicit captured/current configuration policy
   and actor/action idempotency; retain the original run's immutable evidence.
2. Preserve selected run/filter state across refresh, verify replay cursor behavior and
   cancellation races, and complete disconnected/error transitions.
3. Apply additive migrations to the populated fixture database; regenerate OpenAPI/types;
   verify real API/runner and browser interactions before accepting M1.
4. Start M2 with bounded snapshot ingestion and a recoverable index-generation model.
   Keep nonsemantic fixture embeddings clearly labeled until production retrieval is measured.

The authoritative detailed requirements and final checklist remain in
[requirement.md](../requirement.md), especially sections 6, 18 and 21.
