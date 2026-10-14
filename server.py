import asyncio
import json
import logging
import os
import re
import socket
import sqlite3
import tempfile
import time
from collections import deque
from ipaddress import ip_address, ip_network
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, ConfigDict, Field, SecretStr

import api_fns


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
OPENSANCTIONS_DB = Path(os.environ.get("FNS_OPENSANCTIONS_DB", "/var/lib/mcp-fns/opensanctions.sqlite"))
TOOL_NAMES = frozenset({
    "check_contractor", "check_inn", "check_ogrn", "get_legal_status",
    "get_okveds", "get_directors_history", "check_for_red_flags",
})
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("fnsrus")
call_lock = asyncio.Lock()
settings_lock = asyncio.Lock()
recent_calls = deque()
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
    return response


async def call_search_by_name(query):
    if call_lock.locked():
        raise APIError(409, "busy", "Уже выполняется проверка. Дождитесь её завершения.")
    async with call_lock:
        record_call()
        try:
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
                raise api_error from error
            if api_error is not None and api_error.status == 429:
                raise api_error from error
            logger.warning("MCP name search failed (%s)", type(error).__name__)
            raise APIError(503, "search_unavailable", SEARCH_UNAVAILABLE_MESSAGE) from error


def wireguard_control(command):
    if command not in {"status", "connect", "disconnect"}:
        raise ValueError("invalid WireGuard control command")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(35)
            client.connect(str(WIREGUARD_CONTROL_SOCKET))
            client.sendall(json.dumps({"command": command}).encode("utf-8") + b"\n")
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