FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# postgresql-client-16: scripts/backup.sh (pg_dump) and scripts/restore.sh
# (pg_restore) both need the actual client binaries, not just libpq. Pinned
# to 16 (via the PGDG apt repo, not Debian's own — Debian trixie's default
# postgresql-client is 17) to exactly match docker-compose.yml's
# postgres:16 server: a *newer* client can emit directives the server's
# version doesn't understand yet (verified directly: pg_dump 17's
# `SET transaction_timeout = 0;` line makes pg_restore fail against a 16
# server) — matching versions avoids that whole class of bug rather than
# just hoping the direction is safe. Needs build-time internet access to
# apt.postgresql.org; if that's blocked in your build environment, this
# RUN step will fail on the curl call.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY scripts ./scripts

RUN pip install --upgrade pip && pip install -e ".[dev]"
RUN chmod +x scripts/*.sh || true
