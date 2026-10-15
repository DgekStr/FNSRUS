#!/usr/bin/env python3
"""Stream a verified OpenSanctions FTM archive into PostgreSQL in resumable batches."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.import_opensanctions import BATCH_SIZE, MAX_LINE_BYTES, company_row
from scripts.import_opensanctions import DATASET, DATASET_URL, LICENSE_URL
from scripts.import_opensanctions import write_status_file


POSTGRES_DSN = os.environ.get("FNS_OPENSANCTIONS_POSTGRES_DSN", "")
STATUS_FILE = Path(os.environ.get(
    "FNS_OPENSANCTIONS_ARCHIVE_STATUS", "/var/lib/mcp-fns/opensanctions-archive-status.json",
))
META_TABLE = "opensanctions_metadata"
COMPANY_TABLE = "opensanctions_companies"
VERSION_PATTERN = re.compile(r"[0-9]{14}-[a-z0-9]+")
CHECKSUM_PATTERN = re.compile(r"[0-9a-f]{40}")
MIN_FREE_BYTES = 4 * 1024**3


class PostgresImportError(RuntimeError):
    pass


def ensure_import_space(directory: Path) -> None:
    available = shutil.disk_usage(directory).free
    if available < MIN_FREE_BYTES:
        raise PostgresImportError(
            f"PostgreSQL import paused to preserve 4 GiB free space; only {available} bytes remain"
        )


def check_postgres(dsn: str, connect_timeout: int = 3) -> dict:
    if not dsn:
        return {"configured": False, "ready": False, "error": "not_configured"}
    try:
        import psycopg
    except ImportError:
        return {"configured": True, "ready": False, "error": "driver_missing"}
    try:
        with psycopg.connect(dsn, connect_timeout=connect_timeout) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT has_database_privilege(current_database(), 'TEMP'),
                           CASE WHEN current_schema() IS NULL THEN FALSE
                                ELSE has_schema_privilege(current_schema(), 'CREATE') END
                """)
                can_create_temp, can_create_tables = cursor.fetchone()
    except Exception:
        return {"configured": True, "ready": False, "error": "connection_failed"}
    if not can_create_temp or not can_create_tables:
        return {"configured": True, "ready": False, "error": "insufficient_privileges"}
    return {"configured": True, "ready": True, "error": None}


def read_status(status_file: Path) -> dict:
    try:
        value = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def initialize_database(connection) -> None:
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {COMPANY_TABLE} (
                    inn TEXT PRIMARY KEY,
                    ogrn TEXT,
                    name TEXT NOT NULL,
                    city TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    last_seen_version TEXT NOT NULL DEFAULT ''
                )
            """)
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{COMPANY_TABLE}_ogrn ON {COMPANY_TABLE}(ogrn)"
            )
            cursor.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{COMPANY_TABLE}_version ON {COMPANY_TABLE}(last_seen_version)"
            )
            cursor.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{COMPANY_TABLE}_name_fts
                ON {COMPANY_TABLE} USING GIN (to_tsvector('simple', name))
            """)
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {META_TABLE} (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TEMP TABLE IF NOT EXISTS opensanctions_import_batch (
                    sequence_id BIGSERIAL,
                    inn TEXT,
                    ogrn TEXT,
                    name TEXT,
                    city TEXT,
                    entity_id TEXT,
                    last_seen_version TEXT
                ) ON COMMIT DELETE ROWS
            """)


def sync_batch(connection, rows: list[tuple], version: str) -> int:
    if not rows:
        return 0
    with connection.transaction():
        with connection.cursor() as cursor:
            with cursor.copy("""
                COPY opensanctions_import_batch(inn, ogrn, name, city, entity_id, last_seen_version)
                FROM STDIN
            """) as copy:
                for row in rows:
                    copy.write_row((*row, version))
            cursor.execute(f"""
                INSERT INTO {COMPANY_TABLE}(inn, ogrn, name, city, entity_id, last_seen_version)
                SELECT DISTINCT ON (inn) inn, ogrn, name, city, entity_id, last_seen_version
                FROM opensanctions_import_batch
                ORDER BY inn, sequence_id DESC
                ON CONFLICT (inn) DO UPDATE SET
                    ogrn = excluded.ogrn,
                    name = excluded.name,
                    city = excluded.city,
                    entity_id = excluded.entity_id,
                    last_seen_version = excluded.last_seen_version
                WHERE {COMPANY_TABLE}.ogrn IS DISTINCT FROM excluded.ogrn
                   OR {COMPANY_TABLE}.name IS DISTINCT FROM excluded.name
                   OR {COMPANY_TABLE}.city IS DISTINCT FROM excluded.city
                   OR {COMPANY_TABLE}.entity_id IS DISTINCT FROM excluded.entity_id
                   OR {COMPANY_TABLE}.last_seen_version IS DISTINCT FROM excluded.last_seen_version
            """)
            return cursor.rowcount


def update_metadata(connection, values: dict[str, str]) -> None:
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO {META_TABLE}(key, value) VALUES (%s, %s) "
                f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                list(values.items()),
            )


def count_synced(connection, version: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT COUNT(*) FROM {COMPANY_TABLE} WHERE last_seen_version = %s", (version,),
        )
        return cursor.fetchone()[0]


def import_archive(
    archive_path: Path,
    expected_version: str,
    dsn: str = POSTGRES_DSN,
    status_file: Path = STATUS_FILE,
    expected_size: int | None = None,
    expected_checksum: str | None = None,
    expected_entities: int | None = None,
) -> dict:
    if not dsn:
        raise PostgresImportError("FNS_OPENSANCTIONS_POSTGRES_DSN is not configured")
    if not VERSION_PATTERN.fullmatch(expected_version):
        raise ValueError("Expected OpenSanctions version is invalid")
    try:
        import psycopg
    except ImportError as error:
        raise PostgresImportError("psycopg is not installed") from error
    if not archive_path.is_file() or archive_path.is_symlink():
        raise PostgresImportError("Verified OpenSanctions archive is missing")

    status = read_status(status_file)
    if expected_size is None:
        expected_size = status.get("archive_size_bytes", status.get("total_bytes"))
    if expected_size is None:
        expected_size = archive_path.stat().st_size
    source_size = int(expected_size)
    source_checksum = expected_checksum or status.get("archive_checksum", status.get("checksum"))
    if expected_entities is None:
        expected_entities = status.get("expected_entities")
    if not isinstance(source_checksum, str) or not CHECKSUM_PATTERN.fullmatch(source_checksum):
        raise PostgresImportError("Verified archive checksum metadata is missing or invalid")
    if archive_path.stat().st_size != source_size:
        raise PostgresImportError("Archive size does not match verified metadata")

    started_at = datetime.now(timezone.utc).isoformat()
    scanned = 0
    invalid = 0
    changed = 0
    synced = 0
    pending: list[tuple] = []
    stream_size = 0
    stream_hash = hashlib.sha1()
    connection = None
    published = False
    try:
        connection = psycopg.connect(dsn, connect_timeout=5)
        initialize_database(connection)
        synced = count_synced(connection, expected_version)
        update_metadata(connection, {
            "source": "OpenSanctions",
            "dataset": DATASET,
            "dataset_url": DATASET_URL,
            "license": "CC BY-NC 4.0",
            "license_url": LICENSE_URL,
            "sync_state": "postgres_importing",
            "pending_version": expected_version,
            "sync_started_at": started_at,
            "sync_scanned": "0",
            "sync_companies": str(synced),
            "sync_invalid_lines": "0",
            "sync_error": "",
        })
        write_status_file(
            status_file,
            postgres_state="importing",
            postgres_version=expected_version,
            postgres_scanned=0,
            postgres_synced_companies=synced,
            postgres_error=None,
            postgres_started_at=started_at,
        )
        with archive_path.open("rb") as stream:
            for raw_line in stream:
                scanned += 1
                stream_size += len(raw_line)
                stream_hash.update(raw_line)
                if len(raw_line) > MAX_LINE_BYTES:
                    invalid += 1
                elif b'"Company"' in raw_line:
                    try:
                        entity = json.loads(raw_line)
                    except (UnicodeDecodeError, ValueError):
                        invalid += 1
                    else:
                        row = company_row(entity)
                        if row is not None:
                            pending.append(row)
                            if len(pending) >= BATCH_SIZE:
                                ensure_import_space(archive_path.parent)
                                changed += sync_batch(connection, pending, expected_version)
                                pending.clear()
                if scanned % 100_000 == 0:
                    if pending:
                        ensure_import_space(archive_path.parent)
                        changed += sync_batch(connection, pending, expected_version)
                        pending.clear()
                    synced = count_synced(connection, expected_version)
                    update_metadata(connection, {
                        "sync_scanned": str(scanned),
                        "sync_companies": str(synced),
                        "sync_invalid_lines": str(invalid),
                    })
                    write_status_file(
                        status_file,
                        postgres_state="importing",
                        postgres_version=expected_version,
                        postgres_scanned=scanned,
                        postgres_synced_companies=synced,
                        postgres_invalid_lines=invalid,
                        postgres_error=None,
                    )
        if pending:
            ensure_import_space(archive_path.parent)
            changed += sync_batch(connection, pending, expected_version)
            pending.clear()

        latest = read_status(status_file)
        if stream_size != source_size or stream_hash.hexdigest() != source_checksum:
            raise PostgresImportError("Archive size or SHA-1 did not match the verified index")
        if invalid:
            raise PostgresImportError(f"Archive contains {invalid} malformed Company rows")
        if expected_entities is not None and scanned != int(expected_entities):
            raise PostgresImportError(
                f"Archive was incomplete: expected {expected_entities}, scanned {scanned}"
            )
        synced = count_synced(connection, expected_version)
        if not synced:
            raise PostgresImportError("No valid Company entities were found in the archive")
        write_status_file(
            status_file,
            postgres_state="validating",
            postgres_version=expected_version,
            postgres_scanned=scanned,
            postgres_synced_companies=synced,
            postgres_invalid_lines=0,
            postgres_error=None,
        )
        metadata = {
            "version": expected_version,
            "updated_at": str(latest.get("source_updated_at", "")),
            "last_change": str(latest.get("last_source_change", "")),
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "companies": str(synced),
            "records_scanned": str(scanned),
            "invalid_lines": "0",
            "sync_state": "complete",
            "pending_version": "",
            "sync_scanned": str(scanned),
            "sync_companies": str(synced),
            "sync_invalid_lines": "0",
            "sync_error": "",
        }
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute(
                    f"DELETE FROM {COMPANY_TABLE} WHERE last_seen_version != %s", (expected_version,),
                )
                cursor.executemany(
                    f"INSERT INTO {META_TABLE}(key, value) VALUES (%s, %s) "
                    f"ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    list(metadata.items()),
                )
        published = True
    except Exception as error:
        if connection is not None and not published:
            try:
                connection.rollback()
                synced = count_synced(connection, expected_version)
                update_metadata(connection, {
                    "sync_state": "interrupted",
                    "pending_version": expected_version,
                    "sync_scanned": str(scanned),
                    "sync_companies": str(synced),
                    "sync_invalid_lines": str(invalid),
                    "sync_error": f"{type(error).__name__}: {error}",
                })
            except Exception:
                connection.rollback()
        if not published:
            write_status_file(
                status_file,
                postgres_state="interrupted",
                postgres_version=expected_version,
                postgres_scanned=scanned,
                postgres_synced_companies=synced,
                postgres_error=f"{type(error).__name__}: {error}",
            )
        raise
    finally:
        if connection is not None:
            connection.close()

    write_status_file(
        status_file,
        postgres_state="complete",
        postgres_version=expected_version,
        postgres_scanned=scanned,
        postgres_synced_companies=synced,
        postgres_companies_changed=changed,
        postgres_error=None,
        postgres_published_at=datetime.now(timezone.utc).isoformat(),
    )
    return {
        "state": "complete",
        "version": expected_version,
        "scanned": scanned,
        "synced_companies": synced,
        "changed": changed,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-path", type=Path, required=True)
    parser.add_argument("--expected-version", required=True)
    arguments = parser.parse_args()
    try:
        result = import_archive(arguments.archive_path, arguments.expected_version)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        write_status_file(
            STATUS_FILE,
            postgres_state="failed",
            postgres_version=arguments.expected_version,
            postgres_error=f"{type(error).__name__}: {error}",
        )
        print(f"OpenSanctions PostgreSQL import failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
