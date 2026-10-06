from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import create_engine, inspect, select

from app.db.base import Base
from app.models import core  # noqa: F401


def _normalize_sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def _safe_database_identity(url: str) -> tuple[str, str]:
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    return parsed.hostname or "", parsed.path.lstrip("/")


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return _canonical(value.value)
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc)
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"__bytes__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return str(value)


def _table_fingerprint(connection, table) -> tuple[int, str]:
    pk_columns = list(table.primary_key.columns)
    statement = select(table)
    if pk_columns:
        statement = statement.order_by(*pk_columns)

    digest = hashlib.sha256()
    count = 0
    for row in connection.execute(statement):
        payload = {column.name: _canonical(row._mapping[column.name]) for column in table.columns}
        digest.update(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def _run_target_migrations(target_url: str) -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    env["DATABASE_URL"] = target_url
    env["ENVIRONMENT"] = "development"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=backend_dir,
        env=env,
        check=True,
    )


def migrate_database(source_url: str, target_url: str) -> dict[str, dict[str, Any]]:
    if not source_url.startswith("postgresql") or not target_url.startswith("postgresql"):
        raise RuntimeError("Database migration requires PostgreSQL source and target URLs")

    source_identity = _safe_database_identity(source_url)
    target_identity = _safe_database_identity(target_url)
    if source_identity == target_identity:
        raise RuntimeError("Source and target databases resolve to the same database")

    _run_target_migrations(target_url)

    source_engine = create_engine(_normalize_sqlalchemy_url(source_url), pool_pre_ping=True)
    target_engine = create_engine(_normalize_sqlalchemy_url(target_url), pool_pre_ping=True)

    source_tables = set(inspect(source_engine).get_table_names(schema="public"))
    target_tables = set(inspect(target_engine).get_table_names(schema="public"))
    expected_tables = {table.name for table in Base.metadata.tables.values()}
    allowed_extra = {"alembic_version"}

    unexpected_source = source_tables - expected_tables - allowed_extra
    unexpected_target = target_tables - expected_tables - allowed_extra
    missing_source = expected_tables - source_tables
    missing_target = expected_tables - target_tables

    if unexpected_source or unexpected_target or missing_source or missing_target:
        raise RuntimeError(
            "Schema mismatch before migration: "
            f"unexpected_source={sorted(unexpected_source)}, "
            f"unexpected_target={sorted(unexpected_target)}, "
            f"missing_source={sorted(missing_source)}, "
            f"missing_target={sorted(missing_target)}"
        )

    ordered_tables = [table for table in Base.metadata.sorted_tables if table.name in expected_tables]

    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        source_fingerprints = {
            table.name: _table_fingerprint(source_conn, table) for table in ordered_tables
        }
        target_fingerprints = {
            table.name: _table_fingerprint(target_conn, table) for table in ordered_tables
        }

    target_has_data = any(count for count, _ in target_fingerprints.values())
    if target_has_data:
        if source_fingerprints == target_fingerprints:
            return {
                name: {
                    "rows": rows,
                    "sha256": sha,
                    "status": "already-identical",
                }
                for name, (rows, sha) in source_fingerprints.items()
            }
        raise RuntimeError("Target database already contains application data that differs from source")

    with source_engine.connect() as source_conn:
        transaction = source_conn.begin()
        try:
            source_conn.exec_driver_sql(
                "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"
            )
            with target_engine.begin() as target_conn:
                for table in ordered_tables:
                    rows = [dict(row) for row in source_conn.execute(select(table)).mappings().all()]
                    if rows:
                        target_conn.execute(table.insert(), rows)
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise

    result: dict[str, dict[str, Any]] = {}
    with source_engine.connect() as source_conn, target_engine.connect() as target_conn:
        for table in ordered_tables:
            source_count, source_hash = _table_fingerprint(source_conn, table)
            target_count, target_hash = _table_fingerprint(target_conn, table)
            if source_count != target_count or source_hash != target_hash:
                raise RuntimeError(
                    f"Verification failed for table {table.name}: "
                    f"source=({source_count}, {source_hash}), "
                    f"target=({target_count}, {target_hash})"
                )
            result[table.name] = {
                "rows": source_count,
                "sha256": source_hash,
                "status": "verified",
            }

    return result


def run_migration_from_environment(source_url: str) -> dict[str, dict[str, Any]] | None:
    enabled = os.getenv("RUN_DATABASE_MIGRATION_ON_START", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not enabled:
        return None

    target_url = os.getenv("MIGRATION_TARGET_DATABASE_URL", "").strip()
    if not target_url:
        raise RuntimeError(
            "RUN_DATABASE_MIGRATION_ON_START is enabled but MIGRATION_TARGET_DATABASE_URL is missing"
        )

    return migrate_database(source_url, target_url)
