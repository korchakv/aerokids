#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${1:-}"
if [[ -z "${BACKUP_FILE}" || ! -f "${BACKUP_FILE}" ]]; then
  echo "Usage: RESTORE_DATABASE_URL=... $0 /path/to/backup.dump" >&2
  exit 2
fi
if [[ -z "${RESTORE_DATABASE_URL:-}" ]]; then
  echo "RESTORE_DATABASE_URL is required and must point to an isolated disposable database" >&2
  exit 2
fi

SOURCE_URL="${DATABASE_URL_UNPOOLED:-${MIGRATION_DATABASE_URL:-${DATABASE_URL:-}}}"
if [[ -n "${SOURCE_URL}" && "${RESTORE_DATABASE_URL}" == "${SOURCE_URL}" ]]; then
  echo "Refusing to restore into the source/production database" >&2
  exit 3
fi

pg_restore --list "${BACKUP_FILE}" >/dev/null
pg_restore "${RESTORE_DATABASE_URL}" \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  "${BACKUP_FILE}"

(
  cd "$(dirname "$0")/../backend"
  DATABASE_URL="${RESTORE_DATABASE_URL}" MIGRATION_DATABASE_URL="${RESTORE_DATABASE_URL}" \
    python -m app.jobs.audit_invariants
)

echo "Restore drill completed and invariants passed."
