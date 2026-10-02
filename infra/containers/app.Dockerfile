FROM ghcr.io/astral-sh/uv:0.12.22@sha256:f513a91fc62fe7c17567eee97230dd198e43edb8a9fbecca843714a4358fe1bc AS uv
FROM docker:29.2.1-cli@sha256:cab69e2d0a1a2ea9a1ce1060252f439e83483ae41ec09317aecb33b08a0656a5 AS dockercli
FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS backend
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project
COPY apps/api ./apps/api
COPY apps/runner ./apps/runner
COPY migrations ./migrations
COPY alembic.ini ./
COPY fixtures ./fixtures
COPY evaluations ./evaluations
COPY tests ./tests
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/apps/api/src:/app/apps/runner/src" PYTHONUNBUFFERED=1
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
FROM backend AS runner
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
