# M0 architecture gate

Status: **PASSED for the curated M0 boundary slice.**
Final run: 17 passed, 0 failed/errors/skipped, 219.89 seconds; 2026-10-02 18:40 UTC
(2026-10-03 IST). [M0 JUnit evidence](reports/m0-gate.xml) and
[M0 resource measurements](reports/m0-resource-metrics.json) come from real local services.
No architecture tests use mocks or skips. The deterministic model and nonsemantic hash
embedding are explicitly fixture adapters; persistence, broker and execution are real.

| Section 21 scenario | Required evidence | Current status |
|---|---|---|
| Two languages | Python and TS baseline fail, patch passes, immutable harness | PASS: test_01; strict TypeScript compiler marker and actual log artifact |
| Mixed target | Missing React profile yields partial outcome | PASS: test_02; Python + TSX targets, mixed diff, partial verdict |
| Wait releases worker | Concurrency 1, A blocked, B reaches durable wait | PASS: test_03; both leases released while single sandbox occupied |
| Restart/replay | Kill after intent/checkpoint/submission, stable IDs recover | PASS: test_04 (3 cases); real os._exit(86), stable ID/hash, 2 jobs |
| Early completion | Result before wait projection, matching checkpoint resumes | PASS: test_05; actual runner completion before dispatchable projection |
| Broker loss | Recreate empty Redis; accepted work recovers | PASS: test_06; same durable work, exactly 2 logical jobs |
| Cancellation | Setup/test cancellation, sandbox/tmpfs/reservation removed | PASS: test_07 (2 cases); actual parent/child observed, container absent, slot reclaimed within 10s |
| Scale/fencing | Two API + two graph workers; no simultaneous mutation | PASS: test_08 plus stale-fence test; concurrent same-key requests yield one run/2 intents, ownership released |
| Isolation | Cross-tenant vector/artifact denial, no sandbox secrets/network | PASS: test_09; real foreign vectors and recorded foreign log denied; sandbox probe and forged-token denial |
| Upgrade | Paused v1 run resumes after v2 build with v1 executable retained | PASS: test_10; new Docker build retains graph v1, captured profiles unchanged |

```mermaid
sequenceDiagram
  participant API
  participant PG as PostgreSQL
  participant D as Dispatcher/reconciler
  participant C as Redis/Celery
  participant G as Graph segment
  participant CP as PostgreSQL saver
  participant R as Runner
  API->>PG: run + event + command transaction
  D->>PG: claim shared leader, read incomplete command
  D->>C: at-least-once command ID
  C->>G: bounded prefork segment
  G->>PG: advisory ownership, lease/fence, keyed intent
  G->>CP: checkpoint exact pending execution; interrupt
  G->>PG: fenced wait projection + dispatch command
  G-->>C: release graph slot
  D->>R: stable execution ID + input hash
  R->>PG: durable job, shared reservation
  R->>R: hardened sandbox, trusted evaluator, cleanup
  R->>PG: authoritative result before notification
  D->>R: authenticated status polling
  D->>PG: result + matching resume command
  C->>G: new fenced segment
  G->>CP: resume only matching execution/checkpoint
  G->>PG: consume result, evidence-based outcome
```

Reference environment observed: Windows + WSL2 Docker Desktop, 12 logical CPUs,
about 3.5 GiB Docker memory. These are available resources, not measured application usage.
Initial gate topology: 1 API, 1 graph prefork process, 1 dispatcher, 1 runner worker,
1 global sandbox slot; scale scenario temporarily uses 2 APIs + 2 graph workers.
Per-process SQL pool 3 with no overflow; connection acquisition 5s; network 5–10s;
graph segment 25s; Celery hard limit 45s; broker visibility 120s;
sandbox 256MiB/1CPU/64PIDs/24MiB writable tmpfs/64KiB captured log.
Measured metadata latency during two-controller capacity pressure: 20 real GET samples,
p50 16.55ms, p95 33.12ms. Two controllers never exceeded the same single reservation.
Current-profile baseline+patched wall times (including setup/cleanup, 2 samples each):
Python mean 1.420s/max 1.560s; TypeScript mean 5.120s/max 5.456s. These are tiny fixtures,
not a production throughput or peak compiler-memory benchmark.

Point-in-time cgroup memory: API 131.2MiB; graph parent+prefork child 128.7MiB;
dispatcher 131.8MiB; runner API 70.24MiB; controller 91.52MiB; second controller 94.82MiB;
PostgreSQL 51.05MiB; Qdrant 71.19MiB; Redis 6.559MiB; web 14.89MiB.
Test-controller overhead was 146.7MiB. Database size after repeated preserved runs: 13,405,331 bytes.
These samples are neither host-wide RSS nor peak measurements. The scale case temporarily
adds two APIs and two graph workers; the original API remains available while its graph worker stops.

Nine unit checks and three typed modules passed Ruff/mypy validation. Two real Playwright
tests passed in 1.2 minutes: actual TypeScript evidence, Monaco diff, patch download, durable
activity, mixed partial coverage, keyboard navigation and 390px overflow check. Rendered
[desktop evidence](reports/desktop-evidence.png), [diff](reports/desktop-diff.png), and
[mobile evidence](reports/mobile-evidence.png) were visually inspected. CI is defined but
has not run remotely.

Reproduction history is preserved: initial Docker log-driver setup failure, mutable-tag
replica configuration, [cleanup casing regression](reports/cleanup-reproduction.md),
[child-probe failure](reports/strengthened-failure.xml), and
[lease observation race](reports/lease-observation-race.xml). The latter committed review
before bounded worker shutdown; the test now waits at most 5s for actual lease release.
The final full rerun verifies the corrections rather than dismissing failed gates.

Remaining scope: hosted auth and public sandbox hardening, actual semantic embeddings,
generic ingestion, full approval/publication, arbitrary compiler/profile upgrades,
backup/restore and large index/parser/build measurements. M0 acceptance does not imply
R1/R2 or the complete application is finished. The mixed React profile is deliberately
absent here; M4 must add and verify it before claiming full mixed-project coverage.
