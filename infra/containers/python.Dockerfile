FROM python:3.12.14-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
COPY fixtures/repositories /opt/fixtures
COPY evaluations/harness /opt/harness
COPY infra/containers/bootstrap.py /opt/bootstrap.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
