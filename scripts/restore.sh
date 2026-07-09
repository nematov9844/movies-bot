#!/usr/bin/env bash
# Restores the app's Postgres database from a scripts/backup.sh dump
# (plain .dump or gzipped .dump.gz). Destructive: --clean --if-exists
# drops every existing object in the target database before recreating
# it from the dump, so this always asks for confirmation unless -y is
# passed (for scripted/automated use).
#
# Usage: scripts/restore.sh <backup-file.dump[.gz]> [-y]
set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <backup-file.dump[.gz]> [-y]" >&2
  exit 1
fi

DUMP_FILE="$1"
ASSUME_YES="${2:-}"

if [ ! -f "$DUMP_FILE" ]; then
  echo "Fayl topilmadi: $DUMP_FILE" >&2
  exit 1
fi

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# See scripts/backup.sh for why .env is only sourced if present, and why
# any already-set POSTGRES_HOST/PORT has to win over the file's own value —
# same "postgres" (compose network) vs "localhost" (host shell, or the bot
# container's own network_mode: host override) split applies here too.
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

if [ "$ASSUME_YES" != "-y" ]; then
  read -r -p "OGOHLANTIRISH: '$POSTGRES_DB' bazasidagi barcha mavjud ma'lumotlar '$DUMP_FILE' bilan almashtiriladi. Davom etasizmi? [y/N] " confirm
  if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo "Bekor qilindi."
    exit 0
  fi
fi

RESTORE_FILE="$DUMP_FILE"
CLEANUP_FILE=""
if [[ "$DUMP_FILE" == *.gz ]]; then
  RESTORE_FILE="$(mktemp)"
  gunzip -c "$DUMP_FILE" > "$RESTORE_FILE"
  CLEANUP_FILE="$RESTORE_FILE"
fi

PGPASSWORD="$POSTGRES_PASSWORD" pg_restore \
  -h "$POSTGRES_HOST" -p "$POSTGRES_PORT" -U "$POSTGRES_USER" \
  -d "$POSTGRES_DB" --clean --if-exists --no-owner \
  "$RESTORE_FILE"

[ -n "$CLEANUP_FILE" ] && rm -f "$CLEANUP_FILE"

echo "restore tugadi: $DUMP_FILE -> $POSTGRES_DB"
