#!/usr/bin/env python3
"""Stream the OpenSanctions EGRUL export into a compact local FTS5 index."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
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
BATCH_SIZE = 10_000
BATCH_SIZE = 10_000
STATUS_INTERVAL = 100_000
MAX_LINE_BYTES = 2 * 1024**2
DATASET_URL = "https://www.opensanctions.org/datasets/ru_egrul/"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"


class ImportBusyError(RuntimeError):
    pass


class ImportNotReadyError(RuntimeError):
    pass


class InvalidImportDatabaseError(RuntimeError):
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
        "/usr/bin/curl", "--fail", "--location", "--silent", "--show-error", "--compressed",
        "--proxy", PROXY, url,
    ]


def fetch_index() -> dict:
    completed = subprocess.run(
        curl_command(INDEX_URL), check=True, capture_output=True, timeout=120,
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
            entity_id TEXT NOT NULL
        );
        CREATE INDEX idx_companies_ogrn ON companies(ogrn);
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """)
    return connection


def insert_batch(connection: sqlite3.Connection, rows: list[tuple]) -> int:
    if not rows:
        return 0
    before = connection.total_changes
    connection.executemany(
        "INSERT OR IGNORE INTO companies(inn, ogrn, name, city, entity_id) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    connection.commit()
    return connection.total_changes - before


def _import_snapshot_locked() -> dict:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(DATABASE.parent).free < MIN_FREE_BYTES:
        raise RuntimeError("Меньше 4 ГБ свободно; импорт остановлен до скачивания")
    index = fetch_index()
    staging = DATABASE.with_name(f".{DATABASE.name}.{index['version']}.tmp")
    staging.unlink(missing_ok=True)
    connection = create_database(staging)
    process = None
    imported = 0
    seen = 0
    stream_bytes = 0
    stream_hash = hashlib.sha1()
    invalid = 0
    pending: list[tuple] = []
    last_status_at = 0
    staging_ready = False
    write_status(state="running", version=index["version"], source_updated_at=index["updated_at"],
                 last_source_change=index["last_change"], expected_bytes=index["resource_size"],
                 expected_entities=index["entity_count"], imported=0, scanned=0,
                 started_at=datetime.now(UTC).isoformat())
    try:
        process = subprocess.Popen(
            curl_command(index["resource_url"]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        assert process.stdout is not None
        for raw_line in process.stdout:
            seen += 1
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
                            imported += insert_batch(connection, pending)
                            pending.clear()
                            if shutil.disk_usage(DATABASE.parent).free < MIN_FREE_BYTES:
                                raise RuntimeError("Свободное место упало ниже 4 ГБ; импорт остановлен")
            if seen - last_status_at >= STATUS_INTERVAL:
                if pending:
                    imported += insert_batch(connection, pending)
                    pending.clear()
                if shutil.disk_usage(DATABASE.parent).free < MIN_FREE_BYTES:
                    raise RuntimeError("Свободное место упало ниже 4 ГБ; импорт остановлен")
                write_status(state="running", version=index["version"], imported=imported, scanned=seen,
                             invalid_lines=invalid)
                last_status_at = seen
        if pending:
            imported += insert_batch(connection, pending)
            pending.clear()
        return_code = process.wait()
        if return_code != 0:
            error = process.stderr.read(4096).decode("utf-8", errors="replace") if process.stderr else "curl failed"
            raise RuntimeError(f"Загрузка OpenSanctions завершилась с кодом {return_code}: {error[:300]}")
        if stream_bytes != index["resource_size"]:
            raise RuntimeError(f"Размер FTM stream не совпал: ожидалось {index['resource_size']}, получено {stream_bytes}")
        if stream_hash.hexdigest() != index["resource_checksum"]:
            raise RuntimeError("SHA-1 FTM stream не совпал с OpenSanctions index")
        if invalid:
            raise RuntimeError(f"FTM stream содержит некорректные строки: {invalid}")
        expected_entities = index["entity_count"]
        if seen != expected_entities:
            raise RuntimeError(f"FTM stream неполный: ожидалось {expected_entities}, получено {seen}")
        if imported == 0:
            raise RuntimeError("В FTM snapshot не найдено ни одной Company с валидным ИНН")
        write_status(state="indexing", version=index["version"], imported=imported, scanned=seen)
        connection.execute("""
            CREATE VIRTUAL TABLE companies_fts USING fts5(
                name, content='companies', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        connection.execute("INSERT INTO companies_fts(companies_fts) VALUES ('rebuild')")
        metadata = {
            "source": "OpenSanctions",
            "dataset": DATASET,
            "dataset_url": DATASET_URL,
            "license": "CC BY-NC 4.0",
            "license_url": LICENSE_URL,
            "version": index["version"],
            "updated_at": str(index["updated_at"]),
            "last_change": str(index["last_change"]),
            "imported_at": datetime.now(UTC).isoformat(),
            "companies": str(imported),
            "records_scanned": str(seen),
            "invalid_lines": str(invalid),
        }
        connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
        connection.commit()
        connection.execute("PRAGMA optimize")
        write_status(state="validating", version=index["version"], imported=imported, scanned=seen)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RuntimeError("SQLite staging database integrity check failed")
        connection.close()
        connection = None
        result = {"state": "ready_to_publish", "version": index["version"], "imported": imported,
                  "scanned": seen, "expected_entities": expected_entities, "invalid_lines": invalid,
                  "updated_at": index["updated_at"], "last_change": index["last_change"]}
        write_status(**result)
        staging_ready = True
        return result
    except Exception as error:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        write_status(state="failed", version=index["version"], imported=imported, scanned=seen,
                     invalid_lines=invalid, error=f"{type(error).__name__}: {error}")
        raise
    finally:
        if connection is not None:
            connection.close()
        if not staging_ready:
            staging.unlink(missing_ok=True)


def import_snapshot() -> dict:
    with dataset_lock(DATABASE):
        return _import_snapshot_locked()


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


if __name__ == "__main__":
    try:
        result = import_snapshot()
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(f"OpenSanctions import failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)