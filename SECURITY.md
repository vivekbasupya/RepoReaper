# Security policy

RepoReaper is currently a curated local development slice. It is not approved for public
execution of arbitrary, untrusted repositories. Its trusted controller has Docker daemon
access; disposable repository containers do not receive that socket or application secrets.

Read the [local threat model](docs/threat-model/local.md) for assets, trust boundaries,
current controls and remaining hardening. Hosted authentication, least-privilege database
roles and a stronger public execution provider remain future requirements.

## Reporting

Use the repository's **Security → Report a vulnerability** form when available. If it is not
available, open a minimal issue requesting a private reporting channel without exploit
details, credentials, private source or sensitive logs. Do not publish a token or private
repository contents to demonstrate a bug.

Include the affected commit/version, boundary, sanitized reproduction and impact. No response
time or production support commitment is currently promised. There is no bug bounty program.

## Local configuration

Generate local secrets with `scripts/init_env.py`; `.env` is ignored. The checked-in
`local-only` database password is a documented local Compose default. Bind the web proxy to
loopback, leave control services private and disable the gate fault overlay after testing.
Do not use the local cookie bootstrap or demo database credentials for hosted deployment.
