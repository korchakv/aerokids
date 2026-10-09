"""Verify a restored database matches this checkout without applying migrations."""
from __future__ import annotations

import json

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.db.session import engine


def check_migration_head() -> dict:
    expected = set(ScriptDirectory.from_config(Config("alembic.ini")).get_heads())
    with engine.connect() as connection:
        actual = set(MigrationContext.configure(connection).get_current_heads())
    return {"expected": sorted(expected), "actual": sorted(actual), "ok": actual == expected}


if __name__ == "__main__":
    report = check_migration_head()
    print(json.dumps(report))
    raise SystemExit(0 if report["ok"] else 2)
