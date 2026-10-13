import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient

import server
import api_fns


class APITests(unittest.TestCase):
    def setUp(self):
        server.recent_calls.clear()
        server.call_lock = asyncio.Lock()
        server.settings_lock = asyncio.Lock()
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        settings_path = patch.object(api_fns, "SETTINGS_PATH", Path(directory.name) / "settings.json")
        settings_path.start()
        self.addCleanup(settings_path.stop)
        environment = patch.dict(os.environ, {"FNS_API_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(server.app)

    def test_release_version(self):
        self.assertEqual(server.APP_VERSION, "1.0")
        self.assertEqual(server.app.version, server.APP_VERSION)

    def test_api_settings_roundtrip(self):
        headers = {"x-fns-settings": "1", "content-type": "application/json"}

        async def valid_key(key):
            return {"verified_at": "2026-10-13T12:00:00Z", "methods": ["egr", "check"]}

        key = "test-key-not-a-real-secret"
        with patch.object(api_fns, "validate_key", valid_key):
            response = self.client.post("/api/settings/api-fns", headers=headers, json={"api_key": key, "enabled": True})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(key, response.text)
            self.assertTrue(response.json()["enabled"])
            self.assertEqual(api_fns.load_settings()["api_key"], key)
            if os.name != "nt":
                self.assertEqual(api_fns.SETTINGS_PATH.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(key, self.client.get("/api/settings/api-fns").text)
            self.assertEqual(self.client.post("/api/settings/api-fns/test", headers=headers).status_code, 200)
            self.assertFalse(self.client.post("/api/settings/api-fns", headers=headers, json={"enabled": False}).json()["enabled"])
            self.assertFalse(self.client.delete("/api/settings/api-fns", headers=headers).json()["configured"])

    def test_api_settings_registration_link(self):
        key = "fake-registration-key-123"
        headers = {"x-fns-settings": "1", "content-type": "application/json"}

        async def valid_key(received):
            self.assertEqual(received, key)
            return {"verified_at": "2026-10-13T12:00:00Z", "methods": ["egr", "check"]}

        with patch.object(api_fns, "validate_key", valid_key):
            for prefix in ("http://", "https://"):
                response = self.client.post("/api/settings/api-fns", headers=headers,
                                            json={"api_key": f"{prefix}api-fns.ru/api/stat?key={key}", "enabled": True})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(api_fns.load_settings()["api_key"], key)
                self.assertNotIn(key, response.text)
            for link in (f"https://example.com/api/stat?key={key}",
                         f"https://api-fns.ru/api/egr?key={key}",
                         f"https://api-fns.ru/api/stat?key={key}&key=duplicate",
                         "https://api-fns.ru/api/stat?key="):
                response = self.client.post("/api/settings/api-fns", headers=headers, json={"api_key": link, "enabled": True})
                self.assertEqual(response.status_code, 422)
                self.assertNotIn(key, response.text)
                self.assertEqual(api_fns.load_settings()["api_key"], key)
            key = "x" * 256
            response = self.client.post("/api/settings/api-fns", headers=headers,
                                        json={"api_key": f"https://api-fns.ru/api/stat?key={key}", "enabled": True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(api_fns.load_settings()["api_key"], key)
        self.assertEqual(api_fns.normalize_key(f"  {key}  "), key)
        self.assertEqual(api_fns.normalize_key("https://api-fns.ru/api/stat?key=fake-key%2B"), "fake-key+")

    def test_api_settings_security(self):
        response = self.client.post("/api/settings/api-fns", json={"api_key": "test-key", "enabled": True})
        self.assertEqual(response.status_code, 403)
        headers = {"x-fns-settings": "1", "content-type": "application/json", "origin": "http://untrusted.example"}
        self.assertEqual(self.client.delete("/api/settings/api-fns", headers=headers).status_code, 403)
        headers.pop("origin")
        response = self.client.post("/api/settings/api-fns", headers=headers, json={"api_key": "short", "enabled": True})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("short", response.text)
        self.assertEqual(self.client.post("/api/settings/api-fns", headers=headers, json={"enabled": True}).status_code, 422)

    def test_invalid_key_replacement_preserves_saved_key(self):
        api_fns.save_settings({"api_key": "original-fake-key", "enabled": True})
        async def denied(key):
            raise api_fns.ProviderError(403, "api_access_denied", "Ключ отклонён.")
        with patch.object(api_fns, "validate_key", denied):
            response = self.client.post("/api/settings/api-fns", headers={"x-fns-settings": "1"}, json={"api_key": "replacement-fake-key", "enabled": True})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(api_fns.load_settings()["api_key"], "original-fake-key")
        self.assertNotIn("replacement-fake-key", response.text)
        async def exercise():
            await server.settings_lock.acquire()
            try:
                response = self.client.delete("/api/settings/api-fns", headers={"x-fns-settings": "1", "content-type": "application/json"})
                self.assertEqual(response.status_code, 409)
            finally:
                server.settings_lock.release()
        asyncio.run(exercise())

    def test_api_enrichment_preserves_data_and_coverage(self):
        identifier = "7707083893"
        egr = {"items": [{"ЮЛ": {"ИНН": identifier, "ОГРН": "1027700132195", "НаимСокрЮЛ": "Тестовая компания",
                                "Адрес": {"АдресПолн": "Москва"}, "ОснВидДеят": {"Код": "64.19", "Текст": "Банковская деятельность"},
                                "Учредители": [{"НаимПолнЮЛ": "Учредитель"}]}}]}
        analytics = {"items": [{"ЮЛ": {"ИНН": identifier, "Негатив": {"РеестрМассАдрес": "Нет", "РеестрМассРук": "Нет"}}}]}
        base = api_fns.unavailable_report(identifier)
        base["card"] = {"director": {"full_name": "Полученный руководитель", "is_disqualified": False},
                "registration": {"okato": "12345"}}
        base["risks"]["checks_passed"] = ["disqualified_director"]
        base["risks"]["errors"] = [item for item in base["risks"]["errors"] if item["code"] != "disqualified_director"]
        result = api_fns.merge_reports(base, identifier, egr, analytics, [])
        self.assertEqual(result["card"]["address"]["АдресПолн"], "Москва")
        self.assertEqual(result["card"]["director"]["full_name"], "Полученный руководитель")
        self.assertFalse(result["card"]["director"]["is_disqualified"])
        self.assertEqual(result["card"]["registration"]["okato"], "12345")
        self.assertEqual(result["api_fns"]["egr"], egr)
        self.assertEqual(result["risks"]["coverage"]["answered"], 3)
        self.assertEqual(result["risks"]["coverage"]["failed"], 4)
        self.assertEqual(result["verdict_action"], "manual_review_required")
        empty_check = {"items": [{"ЮЛ": {"ИНН": identifier, "Негатив": {}}}]}
        self.assertEqual(api_fns.merge_reports(base, identifier, egr, empty_check, [])["risks"]["coverage"]["answered"], 1)
        analytics["items"][0]["ЮЛ"]["Негатив"]["НедоимкаНалог"] = "Нет"
        self.assertEqual(api_fns.merge_reports(base, identifier, egr, analytics, [])["risks"]["coverage"]["answered"], 3)
        analytics["items"][0]["ЮЛ"]["Негатив"]["НедоимкаНалог"] = "Да (10000 руб.)"
        self.assertEqual(api_fns.merge_reports(base, identifier, egr, analytics, [])["risks"]["coverage"]["flagged"], 1)

    def test_api_enrichment_route_and_fallback(self):
        api_fns.save_settings({"api_key": "test-key-not-real", "enabled": True})
        async def fake_provider(method, key, identifier=None):
            if method == "egr":
                return {"items": [{"ЮЛ": {"ИНН": identifier, "НаимСокрЮЛ": "Из API-ФНС", "Адрес": {"АдресПолн": "Москва"}}}]}
            raise api_fns.ProviderError(403, "api_access_denied", "Нет доступа к аналитике.")
        async def failed_public(name, arguments):
            raise server.APIError(503, "source_unavailable", "Открытый источник недоступен.")
        with patch.object(api_fns, "request_api", fake_provider), patch.object(server, "invoke_mcp", failed_public):
            response = self.client.post("/api/check", json={"identifier": "7707083893"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["card"]["name"]["short"], "Из API-ФНС")
            self.assertEqual(response.json()["risks"]["coverage"]["failed"], 7)
            self.assertNotIn("test-key-not-real", response.text)
            self.assertEqual(self.client.post("/api/check", json={"identifier": "7707083894"}).status_code, 400)

    def test_provider_http_secret_and_errors(self):
        original_client = httpx.AsyncClient
        key = "fake-secret-for-transport-test"
        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.scheme, "https")
            self.assertNotIn(key, str(request.url))
            self.assertIn(key, request.content.decode())
            return httpx.Response(200, json={"Статус": "FREE", "Методы": {"egr": {}, "check": {}}, "key": key, "echo": f"value {key}"})
        def client_factory(**kwargs):
            return original_client(transport=httpx.MockTransport(handler), **kwargs)
        with patch.object(api_fns.httpx, "AsyncClient", client_factory):
            result = asyncio.run(api_fns.request_api("stat", key))
            self.assertNotIn(key, str(result))
            self.assertEqual(asyncio.run(api_fns.validate_key(key))["methods"], ["egr", "check"])
        for status in (403, 429, 503):
            def failed_client(**kwargs):
                return original_client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text=key)), **kwargs)
            with patch.object(api_fns.httpx, "AsyncClient", failed_client):
                with self.assertRaises(api_fns.ProviderError) as caught:
                    asyncio.run(api_fns.request_api("egr", key, "7707083893"))
                self.assertNotIn(key, str(caught.exception))
                self.assertEqual(caught.exception.status, status)

    def test_provider_get_fallback_keeps_key_private(self):
        original_client = httpx.AsyncClient
        key = "fake+fallback&secret=123"
        attempts = []

        def handler(request):
            attempts.append((request.method, request.url.path))
            self.assertEqual(request.url.scheme, "https")
            if request.method == "POST":
                return httpx.Response(403, text="Ошибка: Неверный ключ (1)")
            self.assertEqual(request.url.params["key"], key)
            if request.url.path != "/api/stat":
                self.assertEqual(request.url.params["req"], "7707083893")
            return httpx.Response(200, json={"Статус": "FREE", "Методы": {"egr": {}, "check": {}}, "echo": key})

        def client_factory(**kwargs):
            self.assertFalse(kwargs["follow_redirects"])
            self.assertFalse(kwargs["trust_env"])
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        with patch.object(api_fns.httpx, "AsyncClient", client_factory), self.assertLogs("httpx", level="INFO") as logs:
            self.assertEqual(asyncio.run(api_fns.validate_key(key))["methods"], ["egr", "check"])
            for method in ("egr", "check"):
                result = asyncio.run(api_fns.request_api(method, key, "7707083893"))
                self.assertNotIn(key, str(result))
        self.assertEqual([method for method, path in attempts], ["POST", "GET"] * 3)
        self.assertNotIn(key, "\n".join(logs.output))
        self.assertNotIn("key=", "\n".join(logs.output))

        def denied_client(**kwargs):
            return original_client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text="Ошибка: Неверный ключ (1)")), **kwargs)
        with patch.object(api_fns.httpx, "AsyncClient", denied_client):
            with self.assertRaises(api_fns.ProviderError) as caught:
                asyncio.run(api_fns.validate_key(key))
            self.assertIn("код 1", caught.exception.message)
            self.assertIn("POST и GET", caught.exception.message)
            self.assertNotIn(key, caught.exception.message)

    def test_provider_denial_diagnostics_hide_secrets(self):
        original_client = httpx.AsyncClient
        key = "fake-private-diagnostic-key"
        responses = [
            ("\ufeffОшибка: Неверный ключ (2)", "text/plain; charset=utf-8", "код 2"),
            (f"Ошибка: Доступ с IP запрещён {key}", "text/plain; charset=utf-8", "по IP"),
            (f"<!doctype html><html>Access denied {key}</html>", "text/html", "HTML-страницу"),
            (f"unknown response {key}", "text/plain", "без распознанной причины"),
        ]
        for text, content_type, expected in responses:
            def client_factory(**kwargs):
                return original_client(transport=httpx.MockTransport(lambda request: httpx.Response(403, text=text, headers={"content-type": content_type})), **kwargs)
            with patch.object(api_fns.httpx, "AsyncClient", client_factory), self.assertLogs("fnsrus", level="WARNING") as logs:
                with self.assertRaises(api_fns.ProviderError) as caught:
                    asyncio.run(api_fns.validate_key(key))
            self.assertIn(expected, caught.exception.message)
            self.assertNotIn(key, caught.exception.message)
            self.assertNotIn(key, "\n".join(logs.output))

    def test_stat_without_status_from_provider(self):
        payload = {"ДатаНач": "2026-10-13 14:00:03", "ДатаОконч": "2027-10-13 14:00:03", "Методы": {
            method: {"Лимит": "100", "ТипЛимита": "по запросам", "Истрачено": "1" if method == "egr" else "0"}
            for method in ("bo", "changes", "check", "egr", "innfl", "multinfo", "search", "vyp")}}

        async def statistics(method, key, identifier=None):
            self.assertEqual(method, "stat")
            return payload

        with patch.object(api_fns, "request_api", statistics):
            result = asyncio.run(api_fns.validate_key("fake-stat-key-123"))
            self.assertEqual(result["methods"], ["egr", "check"])
            self.assertTrue(result["verified_at"])
            response = self.client.post("/api/settings/api-fns", headers={"x-fns-settings": "1"},
                                        json={"api_key": "fake-stat-key-123", "enabled": True})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["enabled"])
            self.assertNotIn("fake-stat-key-123", response.text)
            payload.clear()
            with self.assertRaises(api_fns.ProviderError) as caught:
                asyncio.run(api_fns.validate_key("fake-stat-key-123"))
            self.assertEqual(caught.exception.code, "api_invalid_response")

    def test_provider_mismatch_and_red_verdict(self):
        egr = {"items": [{"ЮЛ": {"ИНН": "7707083893", "Статус": "Ликвидировано"}}]}
        with self.assertRaises(api_fns.ProviderError):
            api_fns.company_from(egr, "9999999998")
        base = api_fns.unavailable_report("7707083893")
        result = api_fns.merge_reports(base, "7707083893", egr, None, [])
        self.assertEqual(result["verdict_action"], "impossible_contractor_defunct")
        self.assertEqual(result["legal_status"]["status"], "Ликвидировано")
        egr["items"][0]["ЮЛ"]["Статус"] = "Действующее"
        base["verdict_action"] = "high_risk_do_not_proceed"
        self.assertEqual(api_fns.merge_reports(base, "7707083893", egr, None, [])["verdict_action"], "high_risk_do_not_proceed")

    def test_full_json_is_not_truncated(self):
        payload = {"inn": "7707083893", "card": {"custom_field": {"value": 123}}, "risks": {"errors": ["источник недоступен"]}}

        async def fake_call(name, arguments):
            self.assertEqual(name, "check_contractor")
            self.assertEqual(arguments, {"identifier": "7707083893"})
            return payload

        with patch.object(server, "invoke_mcp", fake_call):
            response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_seven_tools_allowed(self):
        async def fake_call(name, arguments):
            return {"tool": name, "arguments": arguments}

        with patch.object(server, "invoke_mcp", fake_call):
            for name in sorted(server.TOOL_NAMES):
                response = self.client.post(f"/api/tools/{name}", json={"inn": "7707083893"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["tool"], name)

    def test_invalid_format_and_json(self):
        for body in ({"identifier": "bad"}, {"identifier": 7707083893}, {"identifier": "7707083893", "extra": 1}):
            response = self.client.post("/api/check", json=body)
            self.assertEqual(response.status_code, 422)
            self.assertIn("Введите ИНН", response.json()["message"])
        self.assertEqual(self.client.post("/api/check", content="{").status_code, 422)

    def test_unknown_tool(self):
        response = self.client.post("/api/tools/not_a_tool", json={})
        self.assertEqual(response.status_code, 404)

    def test_rate_limit(self):
        server.recent_calls.extend([server.time.monotonic()] * 10)
        response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.assertIn("через минуту", response.json()["message"])

    def test_busy(self):
        async def exercise():
            await server.call_lock.acquire()
            try:
                with self.assertRaises(server.APIError) as caught:
                    await server.call_tool("check_inn", {"inn": "7707083893"})
                self.assertEqual(caught.exception.status, 409)
            finally:
                server.call_lock.release()

        asyncio.run(exercise())

    def test_timeout_and_failure(self):
        for error, expected_status in ((TimeoutError(), 504), (ValueError("broken transport"), 502)):
            async def failing_call(name, arguments):
                raise error

            with patch.object(server, "invoke_mcp", failing_call):
                response = self.client.post("/api/check", json={"identifier": "7707083893"})
            self.assertEqual(response.status_code, expected_status)

    def test_nested_upstream_error(self):
        async def failing_call(name, arguments):
            raise ExceptionGroup("session", [ExceptionGroup("stdio", [server.APIError(404, "not_found", "Контрагент не найден.")])])

        with patch.object(server, "invoke_mcp", failing_call):
            response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["message"], "Контрагент не найден.")

    def test_decode_errors(self):
        result = SimpleNamespace(structured_content={"error": "invalid_input", "message_ru": "Неверная контрольная цифра."}, is_error=False)
        with self.assertRaises(server.APIError) as caught:
            server.decode_result(result)
        self.assertEqual(caught.exception.status, 400)
        result = SimpleNamespace(structured_content=None, content=[SimpleNamespace(type="text", text="broken JSON")], is_error=False)
        with self.assertRaises(server.APIError) as caught:
            server.decode_result(result)
        self.assertEqual(caught.exception.code, "invalid_response")

    def test_cross_site(self):
        response = self.client.post("/api/check", json={"identifier": "7707083893"}, headers={"origin": "http://untrusted.example"})
        self.assertEqual(response.status_code, 403)

    def test_unusable_egrul_card(self):
        result = SimpleNamespace(structured_content={"error": "invalid_input", "message_ru": "ЕГРЮЛ вернул запись без валидного ИНН — дальнейшие проверки невозможны."}, is_error=False)
        with self.assertRaises(server.APIError) as caught:
            server.decode_result(result)
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(caught.exception.code, "invalid_source_data")
        self.assertIn("не получена достоверная карточка", caught.exception.message)

    @unittest.skipUnless(os.environ.get("FNS_LIVE_TESTS") == "1", "live sources are opt-in")
    def test_live_sberbank(self):
        response = self.client.post("/api/check", json={"identifier": "7707083893"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["card"]["inn"], "7707083893")
        self.assertEqual(response.json()["card"]["ogrn"], "1027700132195")
        self.assertIn("coverage", response.json()["risks"])
        self.assertEqual(response.json()["card"]["data_source_meta"]["cache_age_hours"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
class IdentifierValidationTests(unittest.TestCase):
    def test_validate_identifier_rejects_empty_and_unicode_digits(self):
        for identifier in ("", "１２３４５６７８９０", "١٢٣٤٥٦٧٨٩٠"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(api_fns.ProviderError) as error:
                    api_fns.validate_identifier(identifier)
                self.assertEqual(error.exception.status, 400)
                self.assertEqual(error.exception.code, "invalid_input")
