# Contributing to RepoReaper

Read the [README](README.md), [specification](requirement.md),
[design overview](docs/design-overview.md) and [current progress](docs/progress.md) first.
The accepted M0 gate is a foundation; contributions should follow the ordered roadmap.

## Development workflow

1. Fork/clone the project and follow the reproducible local setup. Use Linux containers for
   Celery prefork and execution; native Windows Celery is not a supported worker topology.
2. Create a focused branch, preferably `codex/<change>` or another descriptive feature branch.
3. Keep provider changes behind typed interfaces and retain workspace scope. Record significant
   design choices in `docs/adr` and update progress, limits and setup instructions.
4. Regenerate contracts/types when changing API schemas. Keep dependency lockfiles committed;
   use frozen installs for verification.
5. Run meaningful unit/lint/type/build checks, then the real architecture gate for boundary
   changes and Playwright for rendered interaction changes.
6. Describe the problem, resulting behavior, reproduction evidence, validation and remaining
   limitations in the pull request. Include relevant screenshots for UI changes.

## Required boundaries

- Never execute repository code in API or graph worker processes.
- Use async I/O, bounded blocking threads and separate processes for CPU-heavy work.
- Persist intents and exact checkpoints before external execution, with stable IDs and fencing.
- Share authoritative capacity across replicas; test recovery and cancellation against real services.
- Preserve raw bounded evidence outside patchable source and report incomplete coverage honestly.
- Never commit `.env`, credentials, local databases, caches or installed dependencies.
- Keep deployment, paid calls and application-created PR publication disabled until authorized.

Do not label skipped, mocked or blocked architecture tests as passing. A model fixture adapter
does not stand in for real persistence, broker behavior or sandbox execution.

## Useful checks

```powershell
uv run ruff check .
uv run pytest tests/unit -q
uv run mypy apps/api/src/reporeaper/domain.py apps/api/src/reporeaper/config.py apps/api/src/reporeaper/languages.py
pnpm --dir apps/web install --frozen-lockfile
pnpm --dir apps/web build
pnpm --dir apps/web exec playwright test
```

The complete real-service gate commands are in [README](README.md#real-architecture-gate).
For schema changes, test against populated data and follow the
[upgrade policy](docs/architecture/stability-plan.md).

## Issues and licensing

Use issues for reproducible bugs and focused proposals. Include fixture/language, expected and
observed behavior, sanitized logs, versions and exact reproduction steps. For security concerns,
follow [SECURITY.md](SECURITY.md) instead of posting secrets in a public issue.

No license is selected yet. Discuss contribution/reuse terms with the project owner before
submitting substantial code intended for redistribution.
