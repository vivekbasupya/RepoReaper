# Curated local threat model

Assets: workspace source, checkpoints, artifact hashes, approvals, control credentials.
Trust: API/auth, versioned worker code, dispatcher, runner controller and immutable evaluator
are trusted. Repository files, future model output and repository logs are untrusted.

Runner service is private, authenticated and never exposed by host port. Only the controller
mounts Docker socket. Sandbox runs digest-selected curated images, no network, non-root,
no capabilities, no new privileges, readonly root and bounded tmpfs/resources/logs.
Container removal reclaims process tree and writable disk. Shared capacity is retained until
removal confirms. External evaluator files are outside patchable source. Exit code comes from
Docker state; text "passed" cannot establish success. Original expected failure currently
uses a trusted assertion marker plus nonzero exit and remains limited to curated fixtures.

Every business lookup scopes to workspace membership. Composite foreign keys prevent
cross-workspace references. Qdrant filters inject workspace+snapshot. Artifacts validate
opaque content-addressed keys. Cookies are HttpOnly/SameSite Strict, origins checked.
Local session bootstrap is only safe behind loopback-bound proxy; hosted mode is not enabled.

Remaining hardening before public release: least-privilege separate DB roles, stronger sandbox
host/provider, full CSRF policy and hosted identity, external artifact store, redaction/scanning,
policy-checked arbitrary patch application, broader malicious dependency probes and retention.
