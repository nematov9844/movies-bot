#!/usr/bin/env bash
# Dumps the app's Postgres database, gzips it, and prunes dumps older than
# 7 days. Invoked by Phase 11's daily 03:00 scheduler job (from inside the
# bot container, where POSTGRES_HOST resolves via the compose network) and
# safe to run manually/via cron from the host too.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
set -a
source .env
set +a

BACKUP_DIR="${BACKUP_DIR:-backups}"
mkdir -p "$BACKUP_DIR"

DUMP_FILE="$BACKUP_DIR/db_$(date +%F).dump"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  -Fc -f "$DUMP_FILE" "$POSTGRES_DB"

gzip -f "$DUMP_FILE"

find "$BACKUP_DIR" -name 'db_*.dump.gz' -mtime +7 -delete

echo "backup written: ${DUMP_FILE}.gz"
