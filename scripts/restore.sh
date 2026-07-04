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
set -a
source .env
set +a

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
