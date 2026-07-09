#!/usr/bin/env bash
# Dumps the app's Postgres database, gzips it, and prunes dumps older than
# 7 days. Invoked by Phase 11's daily 03:00 scheduler job (from inside the
# bot container) and safe to run manually/via cron from the host too.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Inside a container, docker-compose's `env_file:` injects every variable
# directly into the process environment — there's no physical .env file to
# read at all (it's gitignored, never COPYd into the image). Only the host
# shell case needs to load it from disk. Preserve any POSTGRES_HOST/PORT
# already set either way: the bot container runs with `network_mode: host`
# (so it can reach a host-local Ollama instance) and is given
# POSTGRES_HOST=localhost directly in docker-compose.yml precisely because
# the compose network's "postgres" hostname doesn't resolve for it; running
# from the plain host shell needs the same override
# (`POSTGRES_HOST=localhost ./scripts/backup.sh`) — a bare `source .env`
# would blow either away with the file's own compose-network default.
: "${POSTGRES_HOST=}" "${POSTGRES_PORT=}"
_pg_host_override="$POSTGRES_HOST"
_pg_port_override="$POSTGRES_PORT"
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
[ -n "$_pg_host_override" ] && POSTGRES_HOST="$_pg_host_override"
[ -n "$_pg_port_override" ] && POSTGRES_PORT="$_pg_port_override"

BACKUP_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"

DUMP_FILE="$BACKUP_DIR/db_$(date +%F).dump"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  -Fc -f "$DUMP_FILE" "$POSTGRES_DB"

gzip -f "$DUMP_FILE"

find "$BACKUP_DIR" -name 'db_*.dump.gz' -mtime +7 -delete

echo "backup written: ${DUMP_FILE}.gz"
