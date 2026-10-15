#!/usr/bin/env python3
"""Stream the OpenSanctions EGRUL export into a compact local FTS5 index."""

from __future__ import annotations

import argparse
import json
import hashlib
import os
import re
import signal
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit


DATASET = "ru_egrul"
INDEX_URL = f"https://data.opensanctions.org/datasets/latest/{DATASET}/index.json"
PROXY = "socks5h://10.8.0.1:19450"
DATABASE = Path(os.environ.get("FNS_OPENSANCTIONS_DB", "/var/lib/mcp-fns/opensanctions.sqlite"))
STATUS_FILE = Path(os.environ.get("FNS_OPENSANCTIONS_STATUS", "/var/lib/mcp-fns/opensanctions-import-status.json"))
MIN_FREE_BYTES = 4 * 1024**3
BATCH_SIZE = 100_000
STATUS_INTERVAL = 100_000
MAX_LINE_BYTES = 2 * 1024**2
MAX_DOWNLOAD_ATTEMPTS = 8
RETRY_BACKOFF_SECONDS = (15, 30, 60, 120, 300, 600, 900)
RETRYABLE_CURL_CODES = {7, 18, 22, 28, 52, 55, 56, 92}
DATASET_URL = "https://www.opensanctions.org/datasets/ru_egrul/"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"


class ImportBusyError(RuntimeError):
    pass


class ImportNotReadyError(RuntimeError):
    pass


class InvalidImportDatabaseError(RuntimeError):
    pass


class RetryableImportError(RuntimeError):
    pass


class ImportStopRequested(RuntimeError):
    pass


@contextmanager
def dataset_lock(database: Path):
    lock_path = database.with_name(f".{database.name}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path.open("a+b")
    locked = False
    try:
        try:
            import fcntl
        except ImportError:
            fcntl = None
        if fcntl is not None:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ImportBusyError("Импорт или публикация уже выполняется") from error
            locked = True
        yield
    finally:
        if locked:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        lock_file.close()


def curl_command(url: str) -> list[str]:
    return [
        "/usr/bin/curl", "--fail", "--location", "--silent", "--show-error", "--compressed", "--http1.1",
        "--connect-timeout", "30", "--speed-time", "120", "--speed-limit", "1024",
        "--proxy", PROXY, url,
    ]


def fetch_index() -> dict:
    completed = subprocess.run(
        curl_command(INDEX_URL), check=True, capture_output=True, timeout=20,
    )
    index = json.loads(completed.stdout)
    version = index.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", version):
        raise ValueError("OpenSanctions index has an invalid dataset version")
    resource = next(
        (item for item in index.get("resources", []) if item.get("name") == "entities.ftm.json"),
        None,
    )
    if not isinstance(resource, dict) or not isinstance(resource.get("url"), str):
        raise ValueError("OpenSanctions index has no entities.ftm.json resource")
    checksum = resource.get("checksum")
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{40}", checksum):
        raise ValueError("OpenSanctions index has no valid SHA-1 checksum for entities.ftm.json")
    resource_url = resource["url"]
    parsed = urlsplit(resource_url)
    if parsed.scheme != "https" or parsed.hostname != "data.opensanctions.org":
        raise ValueError("OpenSanctions resource URL is outside the trusted data host")
    if f"/artifacts/{DATASET}/{version}/" not in parsed.path:
        raise ValueError("OpenSanctions resource version does not match its index")
    return {
        "version": version,
        "updated_at": index.get("updated_at"),
        "last_change": index.get("last_change"),
        "entity_count": int(index.get("entity_count", 0)),
        "resource_url": resource_url,
        "resource_size": int(resource.get("size", 0)),
        "resource_checksum": checksum,
    }


def property_values(properties: dict, key: str) -> list[str]:
    value = properties.get(key)
    values = value if isinstance(value, list) else [value]
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def first_property(properties: dict, *keys: str) -> str | None:
    for key in keys:
        values = property_values(properties, key)
        if values:
            return values[0]
    return None


def company_row(entity: dict) -> tuple | None:
    if entity.get("schema") != "Company":
        return None
    properties = entity.get("properties")
    if not isinstance(properties, dict):
        return None
    inn = first_property(properties, "innCode")
    ogrn = first_property(properties, "ogrnCode")
    names = property_values(properties, "name")
    if not inn or not re.fullmatch(r"[0-9]{10}", inn) or not names:
        return None
    if ogrn and not re.fullmatch(r"[0-9]{13}", ogrn):
        ogrn = None
    name = first_property(properties, "nameShort", "nameFull") or names[-1]
    address = first_property(properties, "address") or ""
    city_match = re.search(r"(?<!\w)(?:г(?:ород)?\.?)\s+([^,;]+)", address, re.IGNORECASE)
    city = city_match.group(1).strip().rstrip(".") if city_match else address.strip()[:30] or "—"
    return inn, ogrn, name, city, str(entity.get("id") or "")


def write_status_file(status_file: Path, **updates) -> None:
    status_file.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    try:
        current = json.loads(status_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    current.update(updates)
    current["updated_at"] = datetime.now(UTC).isoformat()
    descriptor, temporary = tempfile.mkstemp(prefix=".opensanctions-status-", dir=status_file.parent)
    try:
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(current, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, status_file)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_status(**updates) -> None:
    write_status_file(STATUS_FILE, **updates)


def create_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA cache_size=-262144")
    connection.execute("PRAGMA temp_store=FILE")
    connection.executescript("""
        CREATE TABLE companies (
            inn TEXT PRIMARY KEY,
            ogrn TEXT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            last_seen_version TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX idx_companies_ogrn ON companies(ogrn);
        CREATE INDEX idx_companies_last_seen_version ON companies(last_seen_version);
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    return connection


def ensure_live_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = create_database(path) if not path.exists() else sqlite3.connect(path, timeout=30)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA cache_size=-262144")
    connection.execute("PRAGMA temp_store=FILE")
    connection.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            inn TEXT PRIMARY KEY,
            ogrn TEXT,
            name TEXT NOT NULL,
            city TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            last_seen_version TEXT NOT NULL DEFAULT ''
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_companies_ogrn ON companies(ogrn)")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(companies)")}
    if "last_seen_version" not in columns:
        connection.execute("ALTER TABLE companies ADD COLUMN last_seen_version TEXT NOT NULL DEFAULT ''")
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        if metadata.get("version"):
            connection.execute(
                "UPDATE companies SET last_seen_version = ? WHERE last_seen_version = ''",
                (metadata["version"],),
            )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_companies_last_seen_version ON companies(last_seen_version)")
    fts_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'companies_fts'"
    ).fetchone()
    if not fts_exists:
        connection.execute("""
            CREATE VIRTUAL TABLE companies_fts USING fts5(
                name, content='companies', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        connection.execute("INSERT INTO companies_fts(companies_fts) VALUES ('rebuild')")
    connection.executescript("""
        CREATE TRIGGER IF NOT EXISTS companies_ai AFTER INSERT ON companies BEGIN
            INSERT INTO companies_fts(rowid, name) VALUES (new.rowid, new.name);
        END;
        CREATE TRIGGER IF NOT EXISTS companies_ad AFTER DELETE ON companies BEGIN
            INSERT INTO companies_fts(companies_fts, rowid, name) VALUES ('delete', old.rowid, old.name);
        END;
        CREATE TRIGGER IF NOT EXISTS companies_au AFTER UPDATE OF name ON companies BEGIN
            INSERT INTO companies_fts(companies_fts, rowid, name) VALUES ('delete', old.rowid, old.name);
            INSERT INTO companies_fts(rowid, name) VALUES (new.rowid, new.name);
        END;
    """)
    connection.commit()
    return connection


def count_synced_companies(connection: sqlite3.Connection, version: str) -> int:
    return connection.execute(
        "SELECT COUNT(*) FROM companies WHERE last_seen_version = ?", (version,)
    ).fetchone()[0]


def update_metadata(connection: sqlite3.Connection, values: dict[str, str]) -> None:
    connection.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        values.items(),
    )
    connection.commit()


def insert_batch(connection: sqlite3.Connection, rows: list[tuple], version: str = "") -> int:
    if not rows:
        return 0
    cursor = connection.executemany(
        """
        INSERT INTO companies(inn, ogrn, name, city, entity_id, last_seen_version)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(inn) DO UPDATE SET
            ogrn = excluded.ogrn,
            name = excluded.name,
            city = excluded.city,
            entity_id = excluded.entity_id,
            last_seen_version = excluded.last_seen_version
        WHERE companies.ogrn IS NOT excluded.ogrn
           OR companies.name IS NOT excluded.name
           OR companies.city IS NOT excluded.city
           OR companies.entity_id IS NOT excluded.entity_id
           OR companies.last_seen_version IS NOT excluded.last_seen_version
        """,
        [(*row, version) for row in rows],
    )
    connection.commit()
    return max(0, cursor.rowcount)


def download_attempt(connection: sqlite3.Connection, index: dict, attempt: int,
                     prior_imported: int, synced: int, started_at: str) -> dict:
    version = index["version"]
    pending: list[tuple] = []
    imported = 0
    scanned = 0
    stream_bytes = 0
    stream_hash = hashlib.sha1()
    invalid = 0
    last_status_at = 0
    process = None
    write_status(state="running", version=version, source_updated_at=index["updated_at"],
                 last_source_change=index["last_change"], expected_bytes=index["resource_size"],
                 expected_entities=index["entity_count"], attempt=attempt,
                 max_attempts=MAX_DOWNLOAD_ATTEMPTS, retry_in_seconds=0,
                 imported=prior_imported, synced_companies=synced, scanned=0,
                 invalid_lines=0, error=None, started_at=started_at)
    try:
        process = subprocess.Popen(
            curl_command(index["resource_url"]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            scanned += 1
            stream_bytes += len(raw_line)
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
                            imported += insert_batch(connection, pending, version)
                            pending.clear()
                            if shutil.disk_usage(DATABASE.parent).free < MIN_FREE_BYTES:
                                raise RuntimeError("Свободное место упало ниже 4 ГБ; импорт остановлен")
            if scanned - last_status_at >= STATUS_INTERVAL:
                if pending:
                    imported += insert_batch(connection, pending, version)
                    pending.clear()
                if shutil.disk_usage(DATABASE.parent).free < MIN_FREE_BYTES:
                    raise RuntimeError("Свободное место упало ниже 4 ГБ; импорт остановлен")
                synced = count_synced_companies(connection, version)
                update_metadata(connection, {
                    "sync_scanned": str(scanned),
                    "sync_companies": str(synced),
                    "sync_attempt": str(attempt),
                    "sync_invalid_lines": str(invalid),
                    "sync_error": "",
                })
                write_status(state="running", version=version, attempt=attempt,
                             max_attempts=MAX_DOWNLOAD_ATTEMPTS, imported=prior_imported + imported,
                             synced_companies=synced, scanned=scanned,
                             invalid_lines=invalid, error=None)
                last_status_at = scanned
        if pending:
            imported += insert_batch(connection, pending, version)
            pending.clear()
        return_code = process.wait()
        if return_code != 0:
            error = process.stderr.read(4096).decode("utf-8", errors="replace") if process.stderr else "curl failed"
            curl_match = re.search(r"curl: \(([0-9]+)\)", error)
            curl_code = int(curl_match.group(1)) if curl_match else None
            message = f"Загрузка OpenSanctions завершилась с кодом {return_code}: {error[:300]}"
            if curl_code in RETRYABLE_CURL_CODES:
                raise RetryableImportError(message)
            raise RuntimeError(message)
        if stream_bytes != index["resource_size"]:
            raise RetryableImportError(
                f"Размер FTM stream не совпал: ожидалось {index['resource_size']}, получено {stream_bytes}"
            )
        if stream_hash.hexdigest() != index["resource_checksum"]:
            raise RetryableImportError("SHA-1 FTM stream не совпал с OpenSanctions index")
        if invalid:
            raise RuntimeError(f"FTM stream содержит некорректные строки: {invalid}")
        if scanned != index["entity_count"]:
            raise RuntimeError(f"FTM stream неполный: ожидалось {index['entity_count']}, получено {scanned}")
        return {
            "imported": imported,
            "synced_companies": count_synced_companies(connection, version),
            "scanned": scanned,
            "invalid_lines": invalid,
            "stream_bytes": stream_bytes,
        }
    except Exception as error:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        if pending:
            try:
                imported += insert_batch(connection, pending, version)
                pending.clear()
            except sqlite3.DatabaseError:
                connection.rollback()
        error.attempt_imported = imported
        error.attempt_scanned = scanned
        error.attempt_invalid_lines = invalid
        raise


def _import_snapshot_locked(expected_version: str | None = None) -> dict:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    write_status(state="checking", version=expected_version, imported=0, synced_companies=0,
                 scanned=0, invalid_lines=0, error=None, started_at=started_at)
    try:
        if shutil.disk_usage(DATABASE.parent).free < MIN_FREE_BYTES:
            raise RuntimeError("Меньше 4 ГБ свободно; импорт остановлен до скачивания")
        if expected_version is not None and not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", expected_version):
            raise ValueError("Requested OpenSanctions version is invalid")
        index = fetch_index()
        if expected_version is not None and index["version"] != expected_version:
            raise RuntimeError("OpenSanctions snapshot changed after version check; run the version check again")
    except Exception as error:
        write_status(state="failed", version=expected_version, imported=0, scanned=0,
                     error=f"{type(error).__name__}: {error}")
        raise

    connection = None
    total_imported = 0
    last_attempt = {"scanned": 0, "invalid_lines": 0}
    version = index["version"]
    try:
        connection = ensure_live_database(DATABASE)
        synced = count_synced_companies(connection, version)
        update_metadata(connection, {
            "source": "OpenSanctions",
            "dataset": DATASET,
            "dataset_url": DATASET_URL,
            "license": "CC BY-NC 4.0",
            "license_url": LICENSE_URL,
            "sync_state": "running",
            "pending_version": version,
            "sync_started_at": started_at,
            "sync_attempt": "0",
            "sync_scanned": "0",
            "sync_companies": str(synced),
            "sync_invalid_lines": "0",
            "sync_error": "",
        })

        successful_attempt = None
        for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
            try:
                successful_attempt = download_attempt(
                    connection, index, attempt, total_imported, synced, started_at,
                )
                total_imported += successful_attempt["imported"]
                synced = successful_attempt["synced_companies"]
                last_attempt = successful_attempt
                break
            except RetryableImportError as error:
                total_imported += getattr(error, "attempt_imported", 0)
                synced = count_synced_companies(connection, version)
                last_attempt = {
                    "scanned": getattr(error, "attempt_scanned", 0),
                    "invalid_lines": getattr(error, "attempt_invalid_lines", 0),
                }
                if attempt >= MAX_DOWNLOAD_ATTEMPTS:
                    raise
                delay = RETRY_BACKOFF_SECONDS[attempt - 1]
                retry_at = (datetime.now(UTC).timestamp() + delay)
                update_metadata(connection, {
                    "sync_state": "retrying",
                    "pending_version": version,
                    "sync_attempt": str(attempt),
                    "sync_scanned": str(last_attempt["scanned"]),
                    "sync_companies": str(synced),
                    "sync_invalid_lines": str(last_attempt["invalid_lines"]),
                    "sync_error": str(error),
                })
                write_status(
                    state="retrying", version=version, source_updated_at=index["updated_at"],
                    last_source_change=index["last_change"], expected_bytes=index["resource_size"],
                    expected_entities=index["entity_count"], attempt=attempt,
                    max_attempts=MAX_DOWNLOAD_ATTEMPTS, retry_in_seconds=delay,
                    retry_at=datetime.fromtimestamp(retry_at, UTC).isoformat(),
                    imported=total_imported, synced_companies=synced,
                    scanned=last_attempt["scanned"], invalid_lines=last_attempt["invalid_lines"],
                    error=str(error), started_at=started_at,
                )
                time.sleep(delay)

        if successful_attempt is None:
            raise RetryableImportError("Все попытки загрузки исчерпаны")
        scanned = successful_attempt["scanned"]
        invalid = successful_attempt["invalid_lines"]
        expected_entities = index["entity_count"]
        if synced == 0:
            raise RuntimeError("В FTM snapshot не найдено ни одной Company с валидным ИНН")
        write_status(state="validating", version=version, attempt=attempt,
                     max_attempts=MAX_DOWNLOAD_ATTEMPTS, imported=total_imported,
                     synced_companies=synced, scanned=scanned, invalid_lines=invalid, error=None)

        metadata = {
            "source": "OpenSanctions",
            "dataset": DATASET,
            "dataset_url": DATASET_URL,
            "license": "CC BY-NC 4.0",
            "license_url": LICENSE_URL,
            "version": version,
            "updated_at": str(index["updated_at"]),
            "last_change": str(index["last_change"]),
            "imported_at": datetime.now(UTC).isoformat(),
            "companies": str(synced),
            "records_scanned": str(scanned),
            "invalid_lines": str(invalid),
            "sync_state": "complete",
            "pending_version": "",
            "sync_started_at": started_at,
            "sync_attempt": str(attempt),
            "sync_scanned": str(scanned),
            "sync_companies": str(synced),
            "sync_invalid_lines": "0",
            "sync_error": "",
        }
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            metadata.items(),
        )
        connection.execute("DELETE FROM companies WHERE last_seen_version != ?", (version,))
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("SQLite live database integrity check failed")
        connection.commit()
        connection.execute("PRAGMA optimize")
        connection.commit()
        result = {
            "state": "complete", "version": version, "attempt": attempt,
            "imported": total_imported, "synced_companies": synced,
            "scanned": scanned, "expected_entities": expected_entities,
            "invalid_lines": invalid, "updated_at": index["updated_at"],
            "last_change": index["last_change"], "published": True,
        }
        write_status(**result)
        return result
    except Exception as error:
        try:
            connection.rollback()
        except (sqlite3.DatabaseError, AttributeError):
            pass
        try:
            synced = count_synced_companies(connection, version)
            interrupted = isinstance(error, (ImportStopRequested, RetryableImportError))
            update_metadata(connection, {
                "sync_state": "interrupted",
                "pending_version": version,
                "sync_scanned": str(last_attempt["scanned"]),
                "sync_companies": str(synced),
                "sync_invalid_lines": str(last_attempt["invalid_lines"]),
                "sync_error": f"{type(error).__name__}: {error}",
            })
        except (sqlite3.DatabaseError, AttributeError):
            synced = 0
            connection.rollback()
            interrupted = isinstance(error, (ImportStopRequested, RetryableImportError))
        state = "interrupted" if interrupted else "failed"
        write_status(
            state=state, version=version, attempt=attempt if "attempt" in locals() else 0,
            max_attempts=MAX_DOWNLOAD_ATTEMPTS, retry_in_seconds=0,
            synced_companies=synced, scanned=last_attempt["scanned"],
            invalid_lines=last_attempt["invalid_lines"], error=f"{type(error).__name__}: {error}",
        )
        raise
    finally:
        if connection is not None:
            connection.close()


def import_snapshot(expected_version: str | None = None) -> dict:
    with dataset_lock(DATABASE):
        return _import_snapshot_locked(expected_version)


def publish_snapshot(database: Path = DATABASE, status_file: Path = STATUS_FILE) -> dict:
    with dataset_lock(database):
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ImportNotReadyError("Нет завершённого импорта для публикации") from error
        if not isinstance(status, dict) or status.get("state") != "ready_to_publish":
            raise ImportNotReadyError("Импорт ещё не завершён или уже опубликован")
        version = status.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", version):
            raise InvalidImportDatabaseError("Версия staging-базы некорректна")
        staging = database.with_name(f".{database.name}.{version}.tmp")
        if not staging.is_file() or staging.is_symlink():
            raise InvalidImportDatabaseError("Готовая staging-база не найдена")
        if status.get("invalid_lines", 0) != 0:
            raise InvalidImportDatabaseError("В импорте обнаружены некорректные строки")
        try:
            connection = sqlite3.connect(staging.resolve().as_uri() + "?mode=ro", uri=True)
            try:
                integrity = connection.execute("PRAGMA quick_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise InvalidImportDatabaseError("SQLite staging database integrity check failed")
                tables = {row[0] for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
                )}
                if not {"companies", "companies_fts", "metadata"}.issubset(tables):
                    raise InvalidImportDatabaseError("В staging-базе отсутствуют поисковые таблицы")
                metadata = dict(connection.execute("SELECT key, value FROM metadata"))
                company_count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
                fts_count = connection.execute("SELECT COUNT(*) FROM companies_fts").fetchone()[0]
            finally:
                connection.close()
        except (sqlite3.DatabaseError, OSError, ValueError) as error:
            raise InvalidImportDatabaseError("Не удалось проверить staging-базу") from error
        if (metadata.get("version") != version or
                company_count != status.get("imported") or fts_count != company_count or
                metadata.get("records_scanned") != str(status.get("scanned")) or
                metadata.get("invalid_lines") != "0" or
                status.get("scanned") != status.get("expected_entities")):
            raise InvalidImportDatabaseError("Состав staging-базы не совпадает со статусом импорта")
        os.replace(staging, database)
        published_at = datetime.now(UTC).isoformat()
        result = {**status, "state": "complete", "published": True, "published_at": published_at}
        write_status_file(status_file, **result)
        return result


def handle_stop_signal(signum, frame):
    raise ImportStopRequested("Импорт остановлен вручную; синхронизированные batches сохранены")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version")
    arguments = parser.parse_args()

    signal.signal(signal.SIGTERM, handle_stop_signal)
    signal.signal(signal.SIGINT, handle_stop_signal)
    try:
        result = import_snapshot(arguments.expected_version)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(f"OpenSanctions import failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)