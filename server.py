import asyncio
import json
import logging
import os
import re
import socket
import sqlite3
import shutil
import tempfile
import time
from collections import deque
from datetime import datetime, timezone
from ipaddress import ip_address, ip_network
from pathlib import Path
from threading import Lock

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, Field, SecretStr

import api_fns
import scripts.download_opensanctions_archive as opensanctions_archive
import scripts.import_opensanctions as opensanctions_import
import scripts.import_opensanctions_postgres as opensanctions_postgres_import


BASE_DIR = Path(__file__).resolve().parent
APP_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
MCP_VERSION = "0.1.12"
MCP_EGRUL_VERSION = "0.1.10"
CALL_TIMEOUT = 50
EGRUL_CALL_TIMEOUT = CALL_TIMEOUT
MAX_CALLS_PER_MINUTE = 10
MAX_SEARCH_RESULTS = 50
SEARCH_UNAVAILABLE_MESSAGE = "Поиск по названию временно недоступен, введите ИНН"
SEARCH_DATA_UNAVAILABLE_MESSAGE = "База ЕГРЮЛ не загружена. Импортируйте официальный набор данных ФНС."
WIREGUARD_CONTROL_SOCKET = Path(os.environ.get("FNS_WG_CONTROL_SOCKET", "/run/fnsrus-wg-control.sock"))
OPENSANCTIONS_CONTROL_SOCKET = Path(os.environ.get("FNS_OPENSANCTIONS_CONTROL_SOCKET", "/run/fnsrus-import-control.sock"))
OPENSANCTIONS_DB = Path(os.environ.get("FNS_OPENSANCTIONS_DB", "/var/lib/mcp-fns/opensanctions.sqlite"))
OPENSANCTIONS_STATUS_PATH = Path(os.environ.get("FNS_OPENSANCTIONS_STATUS", "/var/lib/mcp-fns/opensanctions-import-status.json"))
OPENSANCTIONS_ARCHIVE_DIR = Path(os.environ.get(
    "FNS_OPENSANCTIONS_ARCHIVE_DIR", "/var/lib/mcp-fns/archives/opensanctions",
))
OPENSANCTIONS_ARCHIVE_STATUS_PATH = Path(os.environ.get(
    "FNS_OPENSANCTIONS_ARCHIVE_STATUS", "/var/lib/mcp-fns/opensanctions-archive-status.json",
))
OPENSANCTIONS_POSTGRES_DSN = os.environ.get("FNS_OPENSANCTIONS_POSTGRES_DSN", "")
OPENSANCTIONS_ENTITY_COUNTS = {"20260912190833-iof": 53_107_328}
TOOL_NAMES = frozenset({
    "check_contractor", "check_inn", "check_ogrn", "get_legal_status",
    "get_okveds", "get_directors_history", "check_for_red_flags",
})
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("fnsrus")
call_lock = asyncio.Lock()
settings_lock = asyncio.Lock()
recent_calls = deque()
opensanctions_progress_samples = deque(maxlen=6)
opensanctions_progress_lock = Lock()
opensanctions_progress_run = None
DEFAULT_SETTINGS_LAN_NETWORKS = "192.168.0.0/24,10.1.17.6/32,127.0.0.0/8,::1/128"


def is_settings_client_allowed(request):
    client = request.client
    if client is None:
        return False
    try:
        address = ip_address(client.host)
    except ValueError:
        return False
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    configured_networks = os.environ.get("FNS_SETTINGS_LAN_NETWORKS", DEFAULT_SETTINGS_LAN_NETWORKS)
    for item in configured_networks.split(","):
        try:
            network = ip_network(item.strip(), strict=False)
        except ValueError:
            continue
        if address.version == network.version and address in network:
            return True
    return False


class APIError(Exception):
    def __init__(self, status, code, message, details=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(strict=True, min_length=1, max_length=200)


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(strict=True, min_length=2, max_length=200)


class WireGuardToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = Field(strict=True)


class WireGuardActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(strict=True, pattern="^(save|enable|disable)$")
    enabled: bool | None = Field(default=None, strict=True)


class OpenSanctionsImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: str = Field(strict=True, min_length=16, max_length=32)


class SettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr | None = Field(default=None, min_length=8, max_length=1024)
    enabled: bool = Field(strict=True)


def decode_result(result):
    payload = result.structured_content
    if payload is None:
        text = next((block.text for block in result.content if block.type == "text"), None)
        if text is None:
            raise APIError(502, "invalid_response", "Источник вернул ответ без данных.")
        try:
            payload = json.loads(text)
        except (ValueError, TypeError) as error:
            raise APIError(502, "invalid_response", "Источник вернул некорректный JSON.") from error
    if not isinstance(payload, dict):
        raise APIError(502, "invalid_response", "Источник вернул данные в неизвестном формате.")
    if result.is_error or payload.get("error"):
        code = str(payload.get("error", "source_error"))
        message = str(payload.get("message_ru") or "Не удалось получить сведения из источника.")
        status = {
            "invalid_input": 400,
            "not_found": 404,
            "contractor_not_found": 404,
            "source_unavailable": 503,
            "rate_limit_exceeded": 429,
            "rate_limit": 429,
        }.get(code, 502)
        if code == "invalid_input" and "ЕГРЮЛ вернул запись без валидного ИНН" in message:
            code = "invalid_source_data"
            status = 503
            message = "По этому ИНН или ОГРН не получена достоверная карточка ЕГРЮЛ. Проверьте номер; если он верный, повторите запрос позже или проверьте выписку ФНС."
        if status == 429:
            message = "Превышен лимит, попробуйте через минуту."
        raise APIError(status, code, message, payload.get("details"))
    return payload


async def invoke_mcp(name, arguments):
    with tempfile.TemporaryDirectory(prefix="fnsrus-") as cache_directory:
        parameters = StdioServerParameters(
            command=os.environ.get("UVX_PATH", "/home/deploy/.local/bin/uvx"),
            args=["--offline", "--from", f"atomno-mcp-fns-check=={MCP_VERSION}", "atomno-mcp-fns-check"],
            env=dict(
                {name: value for name, value in os.environ.items() if name not in {"FNS_API_KEY", "FNS_SETTINGS_TOKEN"}},
                MCP_FNS_HTTP_TIMEOUT="10",
                MCP_FNS_CACHE_DB=str(Path(cache_directory) / "cache.sqlite"),
                MCP_FNS_REGISTRIES_DB=os.environ.get("MCP_FNS_REGISTRIES_DB", str(BASE_DIR / "data" / "registries.sqlite")),
                MCP_FNS_CACHE_TTL_HOURS="0",
                MCP_FNS_LOG_LEVEL="WARNING",
                FASTMCP_CHECK_FOR_UPDATES="off",
                FASTMCP_SHOW_SERVER_BANNER="false",
            ),
        )
        async with asyncio.timeout(CALL_TIMEOUT):
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(reader, writer) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    tool = next((item for item in listing.tools if item.name == name), None)
                    if tool is None:
                        raise APIError(502, "tool_unavailable", "Инструмент отсутствует в установленном MCP-сервере.")
                    if not Draft202012Validator(tool.input_schema).is_valid(arguments):
                        raise APIError(422, "invalid_parameters", "Параметры инструмента не соответствуют его схеме. Проверьте названия и типы полей.")
                    return decode_result(await session.call_tool(name, arguments))


async def invoke_egrul_search(arguments):
    database_path = Path(os.environ.get("MCP_EGRUL_DB", str(BASE_DIR / "data" / "egrul.sqlite")))
    database_path.parent.mkdir(parents=True, exist_ok=True)
    environment = {
        name: value for name, value in os.environ.items()
        if name not in {"FNS_API_KEY", "FNS_SETTINGS_TOKEN", "ATOMNO_API_KEY"}
    }
    environment.update({
        "MCP_EGRUL_DB": str(database_path),
        "MCP_EGRUL_DUMPS_DIR": os.environ.get("MCP_EGRUL_DUMPS_DIR", str(database_path.parent / "dumps")),
        "MCP_EGRUL_LOG_LEVEL": "WARNING",
        "FASTMCP_CHECK_FOR_UPDATES": "off",
        "FASTMCP_SHOW_SERVER_BANNER": "false",
    })
    parameters = StdioServerParameters(
        command=os.environ.get("UVX_PATH", "/home/deploy/.local/bin/uvx"),
        args=["--from", f"atomno-mcp-egrul=={MCP_EGRUL_VERSION}", "atomno-mcp-egrul"],
        env=environment,
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listing = await session.list_tools()
            tools = {item.name: item for item in listing.tools}
            ping_tool = tools.get("ping")
            search_tool = tools.get("search_by_name")
            if ping_tool is None or search_tool is None:
                raise APIError(503, "tool_unavailable", SEARCH_UNAVAILABLE_MESSAGE)
            if not Draft202012Validator(ping_tool.input_schema).is_valid({}):
                raise APIError(503, "invalid_tool_schema", SEARCH_UNAVAILABLE_MESSAGE)
            status = decode_result(await session.call_tool("ping", {}))
            counts = status.get("counts")
            if not isinstance(counts, dict) or not isinstance(counts.get("companies"), int) or counts["companies"] <= 0:
                raise APIError(503, "search_data_unavailable", SEARCH_DATA_UNAVAILABLE_MESSAGE)
            if not Draft202012Validator(search_tool.input_schema).is_valid(arguments):
                raise APIError(503, "invalid_tool_schema", SEARCH_UNAVAILABLE_MESSAGE)
            return decode_result(await session.call_tool("search_by_name", arguments))


def find_api_error(error):
    if isinstance(error, APIError):
        return error
    if isinstance(error, BaseExceptionGroup):
        for nested in error.exceptions:
            found = find_api_error(nested)
            if found is not None:
                return found
    return None


async def call_tool(name, arguments):
    if name not in TOOL_NAMES:
        raise APIError(404, "unknown_tool", "Неизвестный инструмент проверки.")
    if call_lock.locked():
        raise APIError(409, "busy", "Уже выполняется проверка. Дождитесь её завершения.")
    async with call_lock:
        record_call()
        try:
            async with asyncio.timeout(CALL_TIMEOUT):
                settings = api_fns.load_settings()
                if name == "check_contractor" and settings["enabled"] and settings["api_key"]:
                    return await api_fns.enrich_report(arguments.get("identifier"), settings["api_key"], lambda: invoke_mcp(name, arguments))
                return await invoke_mcp(name, arguments)
        except api_fns.ProviderError as error:
            raise APIError(error.status, error.code, error.message) from error
        except TimeoutError as error:
            raise APIError(504, "timeout", "Источники не ответили за 50 секунд. Попробуйте позже.") from error
        except Exception as error:
            api_error = find_api_error(error)
            if api_error is not None:
                raise api_error from error
            logger.error("MCP call failed: %s (%s)", name, type(error).__name__)
            raise APIError(502, "mcp_failure", "Сервис данных временно недоступен. Попробуйте позже.") from error


def record_call():
    current_time = time.monotonic()
    while recent_calls and current_time - recent_calls[0] >= 60:
        recent_calls.popleft()
    if len(recent_calls) >= MAX_CALLS_PER_MINUTE:
        raise APIError(429, "rate_limit", "Превышен лимит, попробуйте через минуту.")
    recent_calls.append(current_time)


def search_city(hit):
    city = hit.get("city")
    if isinstance(city, str) and city.strip():
        return city.strip()
    structured_address = hit.get("address_legal_structured")
    if isinstance(structured_address, dict):
        city = structured_address.get("city")
        if isinstance(city, str) and city.strip():
            return city.strip()
    address = hit.get("address_legal")
    if not isinstance(address, str) or not address.strip():
        return "—"
    city_match = re.search(r"(?<!\w)(?:г(?:ород)?\.?)\s+([^,;]+)", address, re.IGNORECASE)
    if city_match:
        return city_match.group(1).strip().rstrip(".")
    return address.strip()[:30]


def search_opensanctions_database(query):
    if not OPENSANCTIONS_DB.is_file():
        return None
    tokens = [
        "\"" + cleaned + "\"*"
        for token in query.replace('"', " ").split()
        if (cleaned := "".join(character for character in token if character.isalnum() or character == "_"))
        and len(cleaned) >= 2
    ]
    if not tokens:
        return {"results": [], "truncated": False}
    database_uri = OPENSANCTIONS_DB.resolve().as_uri() + "?mode=ro"
    database = sqlite3.connect(database_uri, uri=True, timeout=5)
    try:
        database.row_factory = sqlite3.Row
        rows = database.execute(
            """
            SELECT companies.inn, companies.name, companies.city
            FROM companies_fts
            JOIN companies ON companies.rowid = companies_fts.rowid
            WHERE companies_fts MATCH ?
            ORDER BY bm25(companies_fts)
            LIMIT ?
            """,
            (" AND ".join(tokens), MAX_SEARCH_RESULTS + 1),
        ).fetchall()
        metadata = dict(database.execute("SELECT key, value FROM metadata"))
    finally:
        database.close()
    results = [
        {"name": row["name"], "inn": row["inn"], "city": row["city"] or "—"}
        for row in rows[:MAX_SEARCH_RESULTS]
    ]
    response = {"results": results, "truncated": len(rows) > MAX_SEARCH_RESULTS}
    if metadata:
        response["source"] = metadata.get("source", "OpenSanctions")
        response["dataset"] = metadata.get("dataset", "ru_egrul")
        response["snapshot_date"] = metadata.get("updated_at", "")[:10]
        response["last_source_change"] = metadata.get("last_change", "")[:10]
        response["license"] = metadata.get("license", "CC BY-NC 4.0")
        if metadata.get("sync_state") in {"running", "interrupted"}:
            response["partial_sync"] = True
            response["sync_version"] = metadata.get("pending_version")
            response["synced_companies"] = metadata.get("sync_companies", "0")
    return response


def read_opensanctions_postgres_metadata():
    if not OPENSANCTIONS_POSTGRES_DSN:
        return {}
    try:
        import psycopg
        with psycopg.connect(OPENSANCTIONS_POSTGRES_DSN, connect_timeout=3) as connection:
            rows = connection.execute(
                "SELECT key, value FROM opensanctions_metadata"
            ).fetchall()
    except Exception as error:
        logger.warning("OpenSanctions PostgreSQL metadata unavailable (%s)", type(error).__name__)
        return {}
    return dict(rows)


def search_opensanctions_postgres(query):
    metadata = read_opensanctions_postgres_metadata()
    if not metadata.get("version"):
        return None
    tokens = [
        "".join(character for character in token if character.isalnum() or character == "_")
        for token in query.replace('"', " ").split()
    ]
    tokens = [token for token in tokens if len(token) >= 2]
    if not tokens:
        return {"results": [], "truncated": False}
    tsquery = " & ".join(f"{token}:*" for token in tokens)
    import psycopg
    with psycopg.connect(OPENSANCTIONS_POSTGRES_DSN, connect_timeout=3) as connection:
        rows = connection.execute(
            f"""
            SELECT inn, name, city
            FROM {opensanctions_postgres_import.COMPANY_TABLE}
            WHERE to_tsvector('simple', name) @@ to_tsquery('simple', %s)
            ORDER BY ts_rank(to_tsvector('simple', name), to_tsquery('simple', %s)) DESC
            LIMIT %s
            """,
            (tsquery, tsquery, MAX_SEARCH_RESULTS + 1),
        ).fetchall()
    response = {
        "results": [{"name": row[1], "inn": row[0], "city": row[2] or "—"}
                    for row in rows[:MAX_SEARCH_RESULTS]],
        "truncated": len(rows) > MAX_SEARCH_RESULTS,
        "source": metadata.get("source", "OpenSanctions"),
        "dataset": metadata.get("dataset", "ru_egrul"),
        "snapshot_date": metadata.get("updated_at", "")[:10],
        "last_source_change": metadata.get("last_change", "")[:10],
        "license": metadata.get("license", "CC BY-NC 4.0"),
    }
    if metadata.get("sync_state") in {"postgres_importing", "interrupted"}:
        response["partial_sync"] = True
        response["sync_version"] = metadata.get("pending_version")
        response["synced_companies"] = metadata.get("sync_companies", "0")
    return response


def read_opensanctions_import_status():
    try:
        status = json.loads(OPENSANCTIONS_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}


def read_opensanctions_archive_status():
    try:
        status = json.loads(OPENSANCTIONS_ARCHIVE_STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return status if isinstance(status, dict) else {}


def get_opensanctions_archive_status():
    status = read_opensanctions_archive_status()
    try:
        control_status = import_control("status")
    except APIError:
        control_status = {}
    configured_dir = OPENSANCTIONS_ARCHIVE_DIR.expanduser()
    existing_dir = configured_dir
    while not existing_dir.exists() and existing_dir != existing_dir.parent:
        existing_dir = existing_dir.parent
    available = shutil.disk_usage(existing_dir).free
    postgres_status = opensanctions_postgres_import.check_postgres(OPENSANCTIONS_POSTGRES_DSN)
    archive_path = status.get("archive_path")
    version = status.get("version") or control_status.get("archive_version")
    if not archive_path and isinstance(version, str) and re.fullmatch(r"[0-9]{14}-[a-z0-9]+", version):
        archive_path = str(opensanctions_archive.archive_paths(version, configured_dir)[0])
    return {
        **status,
        "state": status.get("state", "not_started"),
        "archive_path": archive_path,
        "archive_dir": str(configured_dir),
        "available_bytes": available,
        "postgres_configured": postgres_status["configured"],
        "postgres_ready": postgres_status["ready"],
        "postgres_error": postgres_status["error"],
        "archive_active": bool(control_status.get("archive_active")),
        "import_active": bool(control_status.get("import_active")),
        "can_start": control_status.get("ok") is True and not control_status.get("active")
        and postgres_status["ready"],
    }


def reconcile_opensanctions_import_status(control_status):
    status = read_opensanctions_import_status()
    active_states = {"starting", "checking", "running", "retrying", "stopping", "indexing", "validating"}
    if control_status.get("ok") is True and not control_status.get("active") and status.get("state") in active_states:
        opensanctions_import.write_status_file(
            OPENSANCTIONS_STATUS_PATH,
            state="interrupted",
            error="Процесс импорта завершился; синхронизированные batches сохранены.",
            retry_in_seconds=0,
        )
        return read_opensanctions_import_status()
    return status


def read_opensanctions_database_version():
    postgres_metadata = read_opensanctions_postgres_metadata()
    postgres_version = postgres_metadata.get("version")
    if (postgres_metadata.get("sync_state") == "complete" and isinstance(postgres_version, str) and
            re.fullmatch(r"[0-9]{14}-[a-z0-9]+", postgres_version)):
        return postgres_version
    if not OPENSANCTIONS_DB.is_file():
        return None
    try:
        connection = sqlite3.connect(OPENSANCTIONS_DB.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            row = connection.execute("SELECT value FROM metadata WHERE key = 'version'").fetchone()
        finally:
            connection.close()
    except (OSError, sqlite3.DatabaseError, ValueError):
        return None
    version = row[0] if row else None
    return version if isinstance(version, str) and re.fullmatch(r"[0-9]{14}-[a-z0-9]+", version) else None


def opensanctions_version_is_newer(current_version, latest_version):
    if current_version is None:
        return True
    current_match = re.fullmatch(r"([0-9]{14})-[a-z0-9]+", current_version)
    latest_match = re.fullmatch(r"([0-9]{14})-[a-z0-9]+", latest_version)
    if not current_match or not latest_match:
        return False
    return latest_match.group(1) > current_match.group(1) or (
        latest_match.group(1) == current_match.group(1) and latest_version != current_version
    )


def opensanctions_average_rate(status):
    global opensanctions_progress_run
    if status.get("state") not in {"running", "retrying"}:
        with opensanctions_progress_lock:
            opensanctions_progress_samples.clear()
            opensanctions_progress_run = None
        return None
    version = status.get("version")
    started_at = status.get("started_at")
    try:
        scanned = int(status.get("scanned", 0))
        updated_at = datetime.fromisoformat(status["updated_at"].replace("Z", "+00:00"))
        timestamp = updated_at.replace(tzinfo=timezone.utc).timestamp() if updated_at.tzinfo is None else updated_at.timestamp()
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None
    run = (version, started_at, status.get("attempt", 0))
    with opensanctions_progress_lock:
        if opensanctions_progress_run != run:
            opensanctions_progress_samples.clear()
            opensanctions_progress_run = run
        if scanned > 0 and (not opensanctions_progress_samples or
                            scanned > opensanctions_progress_samples[-1][1]):
            opensanctions_progress_samples.append((timestamp, scanned))
        samples = list(opensanctions_progress_samples)
    if len(samples) < 2:
        return None
    elapsed = samples[-1][0] - samples[0][0]
    scanned_delta = samples[-1][1] - samples[0][1]
    if elapsed <= 0 or scanned_delta <= 0:
        return None
    return scanned_delta / elapsed


def get_opensanctions_import_status():
    try:
        control_status = import_control("status")
    except APIError:
        control_status = {}
    status = reconcile_opensanctions_import_status(control_status)
    state = status.get("state", "not_started")
    control_available = control_status.get("ok") is True
    unit_active = bool(control_status.get("import_active", control_status.get("active")))
    archive_active = bool(control_status.get("archive_active"))
    any_unit_active = bool(control_status.get("active"))
    active_states = {"starting", "checking", "running", "retrying", "stopping", "indexing", "validating"}
    unit_starting = unit_active and state not in active_states | {"ready_to_publish"}
    if unit_starting:
        state = "starting"
        status = {
            **status,
            "state": state,
            "version": control_status.get("expected_version") or status.get("version"),
            "scanned": 0,
            "imported": 0,
            "synced_companies": 0,
            "expected_entities": None,
            "updated_at": None,
            "source_updated_at": None,
            "last_source_change": None,
            "last_change": None,
        }
    version = status.get("version")
    try:
        scanned = max(0, int(status.get("scanned", 0)))
        imported = max(0, int(status.get("imported", 0)))
        synced_companies = max(0, int(status.get("synced_companies", imported)))
        expected = int(status.get("expected_entities") or OPENSANCTIONS_ENTITY_COUNTS.get(version, 0))
    except (TypeError, ValueError):
        scanned, imported, synced_companies, expected = 0, 0, 0, 0
    progress = round(min(100, scanned * 100 / expected), 1) if expected > 0 else None
    average_rate = opensanctions_average_rate(status)
    eta_seconds = int((expected - scanned) / average_rate) if average_rate and expected > scanned else None
    staging = None
    if isinstance(version, str) and re.fullmatch(r"[0-9]{14}-[a-z0-9]+", version):
        staging = OPENSANCTIONS_DB.with_name(f".{OPENSANCTIONS_DB.name}.{version}.tmp")
    published_version = read_opensanctions_database_version()
    published = published_version is not None
    can_start_import = control_available and not any_unit_active and state not in active_states | {"ready_to_publish"}
    return {
        "state": state,
        "version": version,
        "published_version": published_version,
        "scanned": scanned,
        "imported": imported,
        "synced_companies": synced_companies,
        "expected_entities": expected or None,
        "progress_percent": progress,
        "average_rate_per_second": round(average_rate, 1) if average_rate else None,
        "eta_seconds": eta_seconds,
        "started_at": status.get("started_at"),
        "updated_at": status.get("updated_at"),
        "attempt": status.get("attempt", 0),
        "max_attempts": status.get("max_attempts"),
        "retry_in_seconds": status.get("retry_in_seconds"),
        "retry_at": status.get("retry_at"),
        "retry_error": status.get("error") if state == "retrying" else None,
        "source_updated_at": status.get("source_updated_at"),
        "last_source_change": status.get("last_source_change", status.get("last_change")),
        "invalid_lines": 0 if state in {"starting", "checking"} or (state == "running" and scanned == 0)
        else status.get("invalid_lines", 0),
        "error": status.get("error") if state in {"failed", "interrupted", "retrying"} else None,
        "published": published,
        "can_publish": state == "ready_to_publish" and staging is not None and staging.is_file(),
        "can_start_import": can_start_import,
        "import_control_available": control_available,
        "unit_active": unit_active,
        "archive_active": archive_active,
    }


async def opensanctions_import_in_progress():
    try:
        control_status = await asyncio.to_thread(import_control, "status")
        status = await asyncio.to_thread(reconcile_opensanctions_import_status, control_status)
        return bool(control_status.get("active")) or status.get("state") in {
            "starting", "checking", "running", "retrying", "stopping", "indexing", "validating", "ready_to_publish",
        }
    except APIError:
        return False


async def call_search_by_name(query):
    if call_lock.locked():
        raise APIError(409, "busy", "Уже выполняется проверка. Дождитесь её завершения.")
    async with call_lock:
        record_call()
        try:
            if OPENSANCTIONS_POSTGRES_DSN:
                async with asyncio.timeout(EGRUL_CALL_TIMEOUT):
                    response = await asyncio.to_thread(search_opensanctions_postgres, query)
                if response is not None:
                    return response
            if OPENSANCTIONS_DB.is_file():
                async with asyncio.timeout(EGRUL_CALL_TIMEOUT):
                    response = await asyncio.to_thread(search_opensanctions_database, query)
                if response is not None:
                    return response
            async with asyncio.timeout(EGRUL_CALL_TIMEOUT):
                payload = await invoke_egrul_search({"query": query, "limit": MAX_SEARCH_RESULTS})
            hits = payload.get("hits")
            if not isinstance(hits, list):
                raise APIError(503, "invalid_search_response", SEARCH_UNAVAILABLE_MESSAGE)
            results = []
            for hit in hits[:MAX_SEARCH_RESULTS]:
                if not isinstance(hit, dict) or not isinstance(hit.get("name"), str) or not isinstance(hit.get("inn"), str):
                    raise APIError(503, "invalid_search_response", SEARCH_UNAVAILABLE_MESSAGE)
                results.append({"name": hit["name"], "inn": hit["inn"], "city": search_city(hit)})
            return {"results": results, "truncated": len(hits) > MAX_SEARCH_RESULTS}
        except Exception as error:
            api_error = find_api_error(error)
            if api_error is not None and api_error.code == "search_data_unavailable":
                import_status = read_opensanctions_import_status()
                if import_status.get("state") == "ready_to_publish":
                    raise APIError(
                        503,
                        "search_import_ready_to_publish",
                        "Импорт завершён; опубликуйте базу в настройках, чтобы включить поиск.",
                    ) from error
                if await opensanctions_import_in_progress():
                    raise APIError(
                        503,
                        "search_import_in_progress",
                        "Идёт загрузка базы OpenSanctions. Поиск станет доступен после завершения импорта.",
                    ) from error
                raise api_error from error
            if api_error is not None and api_error.status == 429:
                raise api_error from error
            logger.warning("MCP name search failed (%s)", type(error).__name__)
            raise APIError(503, "search_unavailable", SEARCH_UNAVAILABLE_MESSAGE) from error


def wireguard_control(command, enabled=None):
    if command not in {"status", "connect", "disconnect", "save", "enable", "disable"}:
        raise ValueError("invalid WireGuard control command")
    if not hasattr(socket, "AF_UNIX"):
        raise APIError(503, "wireguard_control_unavailable", "Управление WireGuard временно недоступно.")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(35)
            client.connect(str(WIREGUARD_CONTROL_SOCKET))
            payload = {"command": command}
            if enabled is not None:
                payload["enabled"] = enabled
            client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            response = client.makefile("rb").readline(4097)
        if len(response) > 4096 or not response.endswith(b"\n"):
            raise ValueError("invalid WireGuard control response size")
        payload = json.loads(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
            raise ValueError("invalid WireGuard control response")
        return payload
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.error("WireGuard control socket failed (%s)", type(error).__name__)
        raise APIError(503, "wireguard_control_unavailable", "Управление WireGuard временно недоступно.") from error


def import_control(command, expected_version=None):
    if command not in {"status", "start", "stop", "archive_start", "archive_stop"}:
        raise ValueError("invalid OpenSanctions control command")
    if not hasattr(socket, "AF_UNIX"):
        raise APIError(503, "import_control_unavailable", "Запуск импорта временно недоступен.")
    payload = {"command": command}
    if expected_version is not None:
        payload["expected_version"] = expected_version
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(180 if command in {"stop", "archive_stop"} else 35 if command in {"start", "archive_start"} else 15)
            client.connect(str(OPENSANCTIONS_CONTROL_SOCKET))
            client.sendall(json.dumps(payload).encode("utf-8") + b"\n")
            response = client.makefile("rb").readline(2049)
        if len(response) > 2048 or not response.endswith(b"\n"):
            raise ValueError("invalid import control response size")
        result = json.loads(response)
        if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
            raise ValueError("invalid import control response")
        return result
    except (OSError, ValueError, json.JSONDecodeError) as error:
        logger.error("OpenSanctions import control socket failed (%s)", type(error).__name__)
        raise APIError(503, "import_control_unavailable", "Запуск импорта временно недоступен.") from error


app = FastAPI(title="ФНС РУС", version=APP_VERSION, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static", check_dir=False), name="static")


@app.exception_handler(APIError)
async def api_error_handler(request, error):
    payload = {"error": error.code, "message": error.message}
    if error.details is not None:
        payload["details"] = error.details
    headers = {"Retry-After": "60"} if error.status == 429 else {}
    return JSONResponse(payload, status_code=error.status, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, error):
    if request.url.path.startswith("/api/settings/"):
        return JSONResponse({"error": "invalid_settings", "message": "Проверьте параметры настроек и формат API-ключа."}, status_code=422)
    if request.url.path == "/api/search":
        return JSONResponse({"error": "invalid_parameters", "message": "Введите название компании минимум из 2 символов."}, status_code=422)
    return JSONResponse(
        {"error": "invalid_parameters", "message": "Введите ИНН из 10 или 12 цифр либо ОГРН из 13 или 15 цифр. Передавайте параметры JSON-объектом."},
        status_code=422,
    )


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    if request.url.path.startswith("/api/settings/") and not is_settings_client_allowed(request):
        return JSONResponse(
            {"error": "local_network_only", "message": "Настройки API доступны только из локальной сети."},
            status_code=403,
            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
        )
    if request.method in {"POST", "DELETE"}:
        origin = request.headers.get("origin")
        if (origin and origin != str(request.base_url).rstrip("/")) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"error": "forbidden", "message": "Запрос с другого сайта запрещён."}, status_code=403)
        if request.url.path.startswith("/api/settings/") and (request.headers.get("x-fns-settings") != "1" or
                request.headers.get("content-type", "").split(";")[0] != "application/json"):
            return JSONResponse({"error": "forbidden", "message": "Изменение настроек доступно только из интерфейса настроек."}, status_code=403)
        if len(await request.body()) > 1024 * 1024:
            return JSONResponse({"error": "body_too_large", "message": "Размер запроса превышает 1 МБ."}, status_code=413)
    if request.method in {"POST", "DELETE"} and request.url.path.startswith("/api/settings/"):
        if settings_lock.locked():
            return JSONResponse({"error": "settings_busy", "message": "Настройки уже изменяются. Дождитесь завершения."}, status_code=409)
        async with settings_lock:
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/", include_in_schema=False)
async def home():
    return FileResponse(BASE_DIR / "templates" / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/explorer/", include_in_schema=False)
async def old_explorer():
    return RedirectResponse("/")


@app.get("/healthz", include_in_schema=False)
async def health():
    return {"status": "ok"}


@app.exception_handler(api_fns.ProviderError)
async def provider_error_handler(request, error):
    return JSONResponse({"error": error.code, "message": error.message}, status_code=error.status)


@app.get("/api/settings/api-fns")
async def get_api_settings():
    return api_fns.public_settings(api_fns.load_settings())


@app.post("/api/settings/api-fns")
async def update_api_settings(body: SettingsRequest):
    data = api_fns.load_settings()
    if body.api_key is not None:
        key = api_fns.normalize_key(body.api_key.get_secret_value())
        data = {"api_key": key, "enabled": body.enabled, **await api_fns.validate_key(key)}
    elif body.enabled:
        if not data["api_key"]:
            raise APIError(422, "key_required", "Введите API-ключ.")
        data.update(await api_fns.validate_key(data["api_key"]))
    data["enabled"] = body.enabled
    api_fns.save_settings(data)
    return api_fns.public_settings(data)


@app.post("/api/settings/api-fns/test")
async def test_api_settings():
    data = api_fns.load_settings()
    if not data["api_key"]:
        raise APIError(422, "key_required", "Сначала сохраните API-ключ.")
    data.update(await api_fns.validate_key(data["api_key"]))
    api_fns.save_settings(data)
    return api_fns.public_settings(data)


@app.delete("/api/settings/api-fns")
async def delete_api_settings():
    data = {"api_key": "", "enabled": False, "verified_at": None, "methods": []}
    api_fns.save_settings(data)
    return api_fns.public_settings(data)


@app.get("/api/settings/wireguard")
async def get_wireguard_settings():
    return await asyncio.to_thread(wireguard_control, "status")


@app.post("/api/settings/wireguard")
async def update_wireguard_settings(body: WireGuardToggleRequest):
    command = "connect" if body.enabled else "disconnect"
    result = await asyncio.to_thread(wireguard_control, command)
    if not result["ok"]:
        code = result.get("error", "wireguard_control_failed")
        status = 409 if code == "not_configured" else 503
        raise APIError(status, code, "Не удалось изменить состояние WireGuard.")
    return result


@app.post("/api/settings/wireguard/action")
async def apply_wireguard_action(body: WireGuardActionRequest):
    if body.action == "save" and body.enabled is None:
        raise APIError(422, "wireguard_autostart_required", "Укажите состояние автозапуска WireGuard.")
    result = await asyncio.to_thread(wireguard_control, body.action, body.enabled)
    if not result["ok"]:
        code = result.get("error", "wireguard_control_failed")
        status = 409 if code == "not_configured" else 503
        raise APIError(status, code, "Не удалось применить действие WireGuard.")
    return result


@app.get("/api/settings/opensanctions")
async def get_opensanctions_settings():
    return await asyncio.to_thread(get_opensanctions_import_status)


@app.get("/api/settings/opensanctions/update-check")
async def check_opensanctions_update():
    try:
        control_status = await asyncio.to_thread(import_control, "status")
    except APIError as error:
        raise APIError(503, "import_control_unavailable", "Запуск импорта временно недоступен.") from error
    status = await asyncio.to_thread(reconcile_opensanctions_import_status, control_status)
    current_version = await asyncio.to_thread(read_opensanctions_database_version)
    if status.get("state") == "ready_to_publish":
        return {
            "decision": "publish_required", "current_version": current_version,
            "latest_version": None, "can_start": False,
        }
    if status.get("state") in {"starting", "checking", "running", "retrying", "stopping", "indexing", "validating"} or control_status.get("active"):
        return {
            "decision": "import_running", "current_version": current_version,
            "latest_version": None, "can_start": False,
        }
    try:
        latest = await asyncio.to_thread(opensanctions_import.fetch_index)
    except Exception as error:
        logger.warning("OpenSanctions version check failed (%s)", type(error).__name__)
        raise APIError(
            503,
            "opensanctions_version_unavailable",
            "Не удалось проверить версию OpenSanctions. Проверьте подключение WireGuard и повторите попытку.",
        ) from error
    latest_version = latest["version"]
    if current_version is None:
        decision = "initial_import"
    elif latest_version == current_version:
        decision = "up_to_date"
    elif opensanctions_version_is_newer(current_version, latest_version):
        decision = "update_available"
    else:
        decision = "upstream_older"
    return {
        "decision": decision,
        "current_version": current_version,
        "latest_version": latest_version,
        "entity_count": latest["entity_count"],
        "source_updated_at": latest["updated_at"],
        "last_source_change": latest["last_change"],
        "can_start": decision in {"initial_import", "update_available"},
    }


@app.post("/api/settings/opensanctions/import")
async def start_opensanctions_import(body: OpenSanctionsImportRequest):
    expected_version = body.expected_version
    if not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", expected_version):
        raise APIError(422, "invalid_import_version", "Версия OpenSanctions указана неверно.")
    try:
        control_status = await asyncio.to_thread(import_control, "status")
    except APIError as error:
        raise APIError(503, "import_control_unavailable", "Запуск импорта временно недоступен.") from error
    status = await asyncio.to_thread(reconcile_opensanctions_import_status, control_status)
    if status.get("state") == "ready_to_publish":
        raise APIError(409, "publish_required", "Сначала опубликуйте завершённую staging-базу.")
    if status.get("state") in {"starting", "checking", "running", "retrying", "stopping", "indexing", "validating"} or control_status.get("active"):
        raise APIError(409, "import_busy", "Импорт уже выполняется.")
    try:
        latest = await asyncio.to_thread(opensanctions_import.fetch_index)
    except Exception as error:
        logger.warning("OpenSanctions version recheck failed (%s)", type(error).__name__)
        raise APIError(
            503,
            "opensanctions_version_unavailable",
            "Не удалось перепроверить версию OpenSanctions. Повторите проверку.",
        ) from error
    latest_version = latest["version"]
    if expected_version != latest_version:
        raise APIError(
            409,
            "snapshot_changed",
            "Снимок OpenSanctions обновился после проверки. Сверьте версии повторно.",
            {"latest_version": latest_version},
        )
    current_version = await asyncio.to_thread(read_opensanctions_database_version)
    if current_version is not None and not opensanctions_version_is_newer(current_version, latest_version):
        raise APIError(409, "no_newer_snapshot", "Уже опубликована последняя доступная версия базы.")
    control_result = await asyncio.to_thread(import_control, "start", latest_version)
    if not control_result["ok"]:
        if control_result.get("error") in {"import_busy", "publish_required"}:
            raise APIError(409, control_result["error"], "Импорт уже запущен или ожидает публикации.")
        raise APIError(503, "import_start_failed", "Не удалось запустить импорт OpenSanctions.")
    return JSONResponse(
        {"state": "starting", "version": latest_version, "entity_count": latest["entity_count"]},
        status_code=202,
    )


@app.post("/api/settings/opensanctions/stop")
async def stop_opensanctions_import(body: OpenSanctionsImportRequest):
    version = body.expected_version
    if not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", version):
        raise APIError(422, "invalid_import_version", "Версия OpenSanctions указана неверно.")
    result = await asyncio.to_thread(import_control, "stop", version)
    if not result["ok"]:
        code = result.get("error", "import_stop_failed")
        if code == "import_not_active":
            raise APIError(409, code, "Этот импорт уже не выполняется.")
        raise APIError(503, code, "Не удалось безопасно остановить импорт.")
    return JSONResponse({"state": "stopping", "version": version}, status_code=202)


@app.get("/api/settings/opensanctions/archive")
async def get_opensanctions_archive_settings():
    return await asyncio.to_thread(get_opensanctions_archive_status)


@app.get("/api/settings/opensanctions/archive/preflight")
async def preflight_opensanctions_archive(expected_version: str):
    if not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", expected_version):
        raise APIError(422, "invalid_import_version", "Версия OpenSanctions указана неверно.")
    try:
        control_status = await asyncio.to_thread(import_control, "status")
    except APIError as error:
        raise APIError(503, "import_control_unavailable", "Проверка systemd недоступна.") from error
    if control_status.get("active"):
        raise APIError(409, "import_busy", "Другой импорт уже выполняется.")
    postgres_status = await asyncio.to_thread(
        opensanctions_postgres_import.check_postgres, OPENSANCTIONS_POSTGRES_DSN,
    )
    index = await asyncio.to_thread(opensanctions_import.fetch_index)
    if index["version"] != expected_version:
        raise APIError(409, "snapshot_changed", "Snapshot обновился; повторите сверку версий.",
                       {"latest_version": index["version"]})
    range_supported = await asyncio.to_thread(opensanctions_archive.probe_range, index)
    plan = await asyncio.to_thread(
        opensanctions_archive.archive_preflight,
        index,
        OPENSANCTIONS_ARCHIVE_DIR,
        opensanctions_archive.POSTGRES_RESERVE_BYTES,
        range_supported,
    )
    return {
        **plan,
        "version": index["version"],
        "entity_count": index["entity_count"],
        "postgres_configured": postgres_status["configured"],
        "postgres_ready": postgres_status["ready"],
        "postgres_error": postgres_status["error"],
        "can_start": plan["space_sufficient"] and postgres_status["ready"],
        "download_mode": "parallel" if range_supported else "single-stream",
    }


@app.post("/api/settings/opensanctions/archive/start")
async def start_opensanctions_archive(body: OpenSanctionsImportRequest):
    expected_version = body.expected_version
    if not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", expected_version):
        raise APIError(422, "invalid_import_version", "Версия OpenSanctions указана неверно.")
    try:
        control_status = await asyncio.to_thread(import_control, "status")
    except APIError as error:
        raise APIError(503, "import_control_unavailable", "Проверка systemd недоступна.") from error
    if control_status.get("active"):
        raise APIError(409, "import_busy", "Другой импорт уже выполняется.")
    postgres_status = await asyncio.to_thread(
        opensanctions_postgres_import.check_postgres, OPENSANCTIONS_POSTGRES_DSN,
    )
    if not postgres_status["ready"]:
        error = postgres_status["error"]
        code = "postgres_not_configured" if error == "not_configured" else "postgres_unavailable"
        raise APIError(503, code, "PostgreSQL недоступен или не имеет нужных прав.")
    index = await asyncio.to_thread(opensanctions_import.fetch_index)
    if index["version"] != expected_version:
        raise APIError(409, "snapshot_changed", "Snapshot обновился; повторите сверку версий.",
                       {"latest_version": index["version"]})
    range_supported = await asyncio.to_thread(opensanctions_archive.probe_range, index)
    plan = await asyncio.to_thread(
        opensanctions_archive.archive_preflight,
        index,
        OPENSANCTIONS_ARCHIVE_DIR,
        opensanctions_archive.POSTGRES_RESERVE_BYTES,
        range_supported,
    )
    if not plan["space_sufficient"]:
        raise APIError(507, "insufficient_archive_space", "Недостаточно свободного места для архива и PostgreSQL.",
                       {"available_bytes": plan["available_bytes"],
                        "required_free_bytes": plan["required_free_bytes"]})
    result = await asyncio.to_thread(import_control, "archive_start", expected_version)
    if not result["ok"]:
        if result.get("error") == "import_busy":
            raise APIError(409, "import_busy", "Другой импорт уже выполняется.")
        raise APIError(503, "archive_start_failed", "Не удалось запустить archive job.")
    return JSONResponse({
        "state": "starting", "version": expected_version,
        "archive_size_bytes": index["resource_size"],
        "download_mode": "parallel" if range_supported else "single-stream",
        "workers": opensanctions_archive.DOWNLOAD_WORKERS if range_supported else 1,
    }, status_code=202)


@app.post("/api/settings/opensanctions/archive/stop")
async def stop_opensanctions_archive(body: OpenSanctionsImportRequest):
    result = await asyncio.to_thread(import_control, "archive_stop", body.expected_version)
    if not result["ok"]:
        code = result.get("error", "archive_stop_failed")
        status = 409 if code == "archive_not_active" else 503
        raise APIError(status, code, "Не удалось остановить archive job.")
    return JSONResponse({"state": "stopping", "version": body.expected_version}, status_code=202)


@app.post("/api/settings/opensanctions/publish")
async def publish_opensanctions_settings():
    try:
        result = await asyncio.to_thread(
            opensanctions_import.publish_snapshot,
            OPENSANCTIONS_DB,
            OPENSANCTIONS_STATUS_PATH,
        )
    except opensanctions_import.ImportBusyError as error:
        raise APIError(409, "import_busy", str(error)) from error
    except opensanctions_import.ImportNotReadyError as error:
        raise APIError(409, "import_not_ready", str(error)) from error
    except opensanctions_import.InvalidImportDatabaseError as error:
        logger.warning("OpenSanctions staging validation failed (%s)", type(error).__name__)
        raise APIError(
            422,
            "invalid_import_database",
            "Проверка staging-базы не пройдена; текущая база не изменена.",
        ) from error
    return {key: result.get(key) for key in ("state", "version", "imported", "scanned", "published_at")}


@app.post("/api/check")
async def check_contractor(body: CheckRequest):
    identifier = body.identifier.strip()
    if not identifier:
        raise APIError(422, "invalid_parameters", "Введите ИНН, ОГРН или название компании.")
    if re.fullmatch(r"[0-9]+", identifier):
        if len(identifier) not in {10, 12, 13, 15}:
            raise APIError(422, "invalid_parameters", "Введите ИНН из 10 или 12 цифр либо ОГРН из 13 или 15 цифр.")
        return await call_tool("check_contractor", {"identifier": identifier})
    if len(identifier) < 2:
        raise APIError(422, "invalid_parameters", "Введите название компании минимум из 2 символов.")
    return await call_search_by_name(identifier)


@app.post("/api/search")
async def search_by_name(body: SearchRequest):
    query = body.query.strip()
    if len(query) < 2:
        raise APIError(422, "invalid_parameters", "Введите название компании минимум из 2 символов.")
    return await call_search_by_name(query)


@app.post("/api/tools/{tool_name}")
async def run_tool(tool_name: str, arguments: dict):
    return await call_tool(tool_name, arguments)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )