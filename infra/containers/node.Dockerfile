FROM node:22.20.0-slim@sha256:b21fe589dfbe5cc39365d0544b9be3f1f33f55f3c86c87a76ff65a02f8f5848e
COPY infra/containers/node-profile /opt/toolchain
RUN cd /opt/toolchain && npm ci --ignore-scripts --no-audit --no-fund
COPY fixtures/repositories /opt/fixtures
COPY evaluations/harness /opt/harness
COPY infra/containers/bootstrap.mjs /opt/bootstrap.mjs
USER 10001:10001
