# Stability and upgrade plan

| Change | Boundary | Acceptance evidence |
|---|---|---|
| Add language | Explicit LanguageAdapter registry, profile, fixture | Same run/execution DTOs; per-target checks |
| Change coding provider | ModelAdapter, captured config | Typed patch flow and evidence stay intact |
| Change embedding | New collection/generation, captured metadata | Old snapshots/index IDs remain readable |
| Increase capacity | Deployment + shared reservation configuration | Two replicas cannot exceed shared slots |
| Replace sandbox | SandboxProvider submit/status/cancel | Same stable ID/hash, provenance/recovery tests |
| Local to hosted | Auth, artifacts, repository/provider wiring | Existing tenant FK/access tests; stronger execution isolation |
| Upgrade graph/payload/schema | Executable graph registry + versioned DTOs + migrations | Paused-run and populated migration tests |

Graph v1 code remains available until all v1 runs drain. New builds must not silently
reinterpret its checkpoints. Unsupported versions enter waiting_input with restart/export
instructions. Commands and events have schema_version=1. Runs capture graph/prompt/model/index/
profile config and exact Python/Node image digests before acceptance; changes apply to new
runs. Each execution records its actual toolchain, evaluator, source and patch hashes.
The upgrade gate changes the deployment image while retaining graph v1 and the same
runtime profiles. It proves executable retention, not arbitrary checkpoint or compiler
migration. A future profile change must retain an explicit approved digest registry for
active runs or hold incompatible work with a reason and restart/export path. Never substitute
the current mutable image tag for a captured digest. Experimental pre-pin runs are held.

Use expand/backfill/contract migrations. Take PostgreSQL and artifact backups before schema
deployment; application rollback does not imply database downgrade. Migration runs once under
shared advisory lock with SQL lock timeout. LangGraph owns tables in `checkpoints` schema.
Qdrant is rebuildable. Fixture collection v1 is nonsemantic and must be replaced with a new
production generation rather than being relabeled semantic.

All structural changes after M0 require a measured reason and ADR. See gate-report.md
for definitive acceptance rather than assuming a passing unit suite proves the boundaries.

## Upgrade validation and release discipline

Reproduce frozen dependencies and migrations before changing providers. The executable v1
implementation is retained; new versions require an explicit registry entry. Unsupported
graph/command versions have a persisted error, not a silent reinterpretation. Retain raw
artifacts and the original result hashes when offering a fresh run.

For additive migrations, apply against this populated fixture database and demonstrate that
existing run, intent, checkpoint and artifact rows remain readable. Test backup/restore and
large-table migration costs before hosted acceptance. Neither is claimed by the M0 gate.

The initial SQL budget is three pooled connections per application process with zero overflow,
plus one checkpoint connection per active graph segment. Reserve deployment/test headroom
within PostgreSQL's 100-connection default. Increasing replicas requires calculating this sum
and rerunning shared capacity/fencing tests. Keep one sandbox slot on the measured 3.5 GiB
local engine; measured RSS is lower than configured caps. Caps alone are not a reservation of
physical RAM. Node/JVM/Go build peaks and production parser/index workloads remain M2/R2
measurements; do not infer those capacities from tiny boundary fixtures.
