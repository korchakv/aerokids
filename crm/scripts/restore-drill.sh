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
if [[ -z "${SOURCE_URL}" ]]; then
  echo "A source database URL is required to protect production from restore" >&2
  exit 3
fi
SOURCE_LIBPQ="${SOURCE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
RESTORE_LIBPQ="${RESTORE_DATABASE_URL/postgresql+psycopg:\/\//postgresql:\/\/}"
RESTORE_SQLALCHEMY="${RESTORE_DATABASE_URL}"
if [[ "${RESTORE_SQLALCHEMY}" == postgresql://* ]]; then
  RESTORE_SQLALCHEMY="postgresql+psycopg://${RESTORE_SQLALCHEMY#postgresql://}"
fi

# Compare database identity rather than passwords, driver markers or SSL options.
# Neon pooled and direct endpoints address the same database.
SOURCE_DATABASE_URL="${SOURCE_LIBPQ}" python - <<'PY'
import os
import sys
from urllib.parse import unquote, urlsplit


def identity(value):
    url = urlsplit(value.replace("postgresql+psycopg://", "postgresql://", 1))
    if url.scheme not in {"postgresql", "postgres"} or not url.hostname or not url.path.strip("/"):
        raise ValueError("An explicit PostgreSQL host and database are required")
    host = url.hostname.rstrip(".").lower()
    if host.endswith(".neon.tech"):
        label, rest = host.split(".", 1)
        host = label.removesuffix("-pooler") + "." + rest
    return host, url.port or 5432, unquote(url.path.lstrip("/"))


try:
    same_database = identity(os.environ["SOURCE_DATABASE_URL"]) == identity(os.environ["RESTORE_DATABASE_URL"])
except ValueError:
    print("Invalid source or restore database identity: explicit PostgreSQL host and database required", file=sys.stderr)
    sys.exit(3)
if same_database:
    print("Refusing to restore into the source/production database", file=sys.stderr)
    sys.exit(3)
PY

pg_restore --list "${BACKUP_FILE}" >/dev/null
pg_restore --dbname="${RESTORE_LIBPQ}" \
  --exit-on-error \
  --single-transaction \
  --clean \
  --if-exists \
  --no-owner \
  --no-acl \
  "${BACKUP_FILE}"

(
  cd "$(dirname "$0")/../backend"
  DATABASE_URL="${RESTORE_SQLALCHEMY}" MIGRATION_DATABASE_URL="${RESTORE_SQLALCHEMY}" \
    python -m app.jobs.check_migration_head
  DATABASE_URL="${RESTORE_SQLALCHEMY}" MIGRATION_DATABASE_URL="${RESTORE_SQLALCHEMY}" \
    python -m app.jobs.audit_invariants
)

echo "Restore drill completed and invariants passed."
