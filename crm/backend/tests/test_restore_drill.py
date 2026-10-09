from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

from app.jobs import check_migration_head


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "restore-drill.sh"
SOURCE = "postgresql://backup@ep-example.eu-central-1.aws.neon.tech/neondb?sslmode=require"


@pytest.fixture
def drill(tmp_path):
    archive = tmp_path / "backup.dump"
    archive.touch()
    calls = tmp_path / "calls.jsonl"
    commands = tmp_path / "bin"
    commands.mkdir()
    pg_restore = commands / "pg_restore"
    pg_restore.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['DRILL_CALLS'], 'a') as out:\n"
        "    out.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "sys.exit(int(os.environ.get('RESTORE_EXIT', '0')) if '--list' not in sys.argv else 0)\n"
    )
    pg_restore.chmod(0o700)
    python = commands / "python"
    python.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "if sys.argv[1] == '-':\n"
        f"    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])\n"
        "with open(os.environ['DRILL_CALLS'], 'a') as out:\n"
        "    out.write(sys.argv[-1] + '\\n')\n"
        "sys.exit(int(os.environ.get('MIGRATION_EXIT', '0')) if sys.argv[-1].endswith('check_migration_head') else 0)\n"
    )
    python.chmod(0o700)

    def run(target, *, source=SOURCE, **extra):
        env = {key: value for key, value in os.environ.items() if key not in {
            "DATABASE_URL", "DATABASE_URL_UNPOOLED", "MIGRATION_DATABASE_URL", "RESTORE_DATABASE_URL",
        }}
        env.update(PATH=f"{commands}:{env['PATH']}", RESTORE_DATABASE_URL=target, DRILL_CALLS=str(calls), **extra)
        if source:
            env["DATABASE_URL_UNPOOLED"] = source
        result = subprocess.run(["bash", str(SCRIPT), str(archive)], env=env, capture_output=True, text=True)
        return result, calls.read_text().splitlines() if calls.exists() else []

    return run, archive


@pytest.mark.parametrize("target", [
    SOURCE,
    "postgresql+psycopg://other@ep-example.eu-central-1.aws.neon.tech:5432/neondb?sslmode=verify-full",
    "postgres://other@ep-example-pooler.eu-central-1.aws.neon.tech/neondb",
])
def test_refuses_source_database_before_restore(drill, target):
    run, _ = drill
    result, calls = run(target)
    assert result.returncode == 3
    assert calls == []
    assert SOURCE not in result.stderr


def test_requires_source_database(drill):
    run, _ = drill
    result, calls = run("postgresql://backup@isolated/neondb", source=None)
    assert result.returncode == 3
    assert calls == []


def test_restores_to_explicit_isolated_database_and_checks_migrations_first(drill):
    run, archive = drill
    target = "postgresql://backup@isolated/neondb"
    result, calls = run(target)
    assert result.returncode == 0, result.stderr
    args = json.loads(calls[1])
    assert f"--dbname={target}" in args
    assert "--single-transaction" in args
    assert "--exit-on-error" in args
    assert args[-1] == str(archive)
    assert calls[2:] == ["app.jobs.check_migration_head", "app.jobs.audit_invariants"]


def test_restore_failure_stops_before_audits(drill):
    run, _ = drill
    result, calls = run("postgresql://backup@isolated/neondb", RESTORE_EXIT="1")
    assert result.returncode == 1
    assert len(calls) == 2
    assert "completed" not in result.stdout


def test_old_migration_stops_before_invariant_success(drill):
    run, _ = drill
    result, calls = run("postgresql://backup@isolated/neondb", MIGRATION_EXIT="2")
    assert result.returncode == 2
    assert calls[-1] == "app.jobs.check_migration_head"
    assert "completed" not in result.stdout


@pytest.mark.parametrize("revision", [None, "0025_subscription_rule_snapshots", "current"])
def test_migration_check_requires_exact_checkout_heads(monkeypatch, revision):
    engine = create_engine("sqlite://")
    monkeypatch.setattr(check_migration_head, "engine", engine)
    expected = check_migration_head.check_migration_head()["expected"]
    if revision:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(100) NOT NULL)"))
            connection.execute(text("INSERT INTO alembic_version VALUES (:revision)"), {
                "revision": expected[0] if revision == "current" else revision,
            })
    assert check_migration_head.check_migration_head()["ok"] == (revision == "current")
    engine.dispose()
