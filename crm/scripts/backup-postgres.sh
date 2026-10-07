#!/usr/bin/env bash
set -euo pipefail

DB_URL="${DATABASE_URL_UNPOOLED:-${MIGRATION_DATABASE_URL:-${DATABASE_URL:-}}}"
if [[ -z "${DB_URL}" ]]; then
  echo "DATABASE_URL_UNPOOLED, MIGRATION_DATABASE_URL or DATABASE_URL is required" >&2
  exit 2
fi

# PostgreSQL CLI tools use libpq URLs and do not understand SQLAlchemy's
# explicit +psycopg driver marker.
PG_DUMP_URL="${DB_URL/postgresql+psycopg:\/\//postgresql:\/\/}"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}" || true

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT="${BACKUP_DIR}/schoolcrm-${STAMP}.dump"

pg_dump "${PG_DUMP_URL}" \
  --format=custom \
  --no-owner \
  --no-acl \
  --file="${OUTPUT}"

chmod 600 "${OUTPUT}" || true
pg_restore --list "${OUTPUT}" >/dev/null

echo "Backup created and validated: ${OUTPUT}"
