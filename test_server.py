import asyncio
import hashlib
import io
import json
import sqlite3
import os
import runpy
import sys
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from fastapi.testclient import TestClient

import server
import api_fns
import scripts.import_opensanctions as opensanctions_import
import scripts.import_opensanctions_postgres as opensanctions_postgres_import
import scripts.fnsrus_import_control as fnsrus_import_control
import scripts.download_opensanctions_archive as opensanctions_archive
from scripts.import_opensanctions import company_row, create_database, insert_batch
from scripts.install_opensanctions_proxy import build_proxy_config


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
        import_status_path = patch.object(server, "OPENSANCTIONS_STATUS_PATH", Path(directory.name) / "import-status.json")
        import_status_path.start()
        self.addCleanup(import_status_path.stop)
        archive_dir = patch.object(server, "OPENSANCTIONS_ARCHIVE_DIR", Path(directory.name) / "archives")
        archive_dir.start()
        self.addCleanup(archive_dir.stop)
        archive_status_path = patch.object(
            server, "OPENSANCTIONS_ARCHIVE_STATUS_PATH", Path(directory.name) / "archive-status.json",
        )
        archive_status_path.start()
        self.addCleanup(archive_status_path.stop)
        postgres_dsn = patch.object(server, "OPENSANCTIONS_POSTGRES_DSN", "")
        postgres_dsn.start()
        self.addCleanup(postgres_dsn.stop)
        database_path = patch.object(server, "OPENSANCTIONS_DB", Path(directory.name) / "opensanctions.sqlite")
        database_path.start()
        self.addCleanup(database_path.stop)
        self.import_control_function = server.import_control
        import_control = patch.object(server, "import_control", return_value={"ok": True, "active": False})
        import_control.start()
        self.addCleanup(import_control.stop)
        server.opensanctions_progress_samples.clear()
        server.opensanctions_progress_run = None
        environment = patch.dict(os.environ, {
            "FNS_API_KEY": "",
            "FNS_SETTINGS_LAN_NETWORKS": "192.168.0.0/24,10.1.17.6/32,127.0.0.0/8,::1/128",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(server.app, client=("192.168.0.10", 12345))

    def test_release_version(self):
        self.assertEqual(server.APP_VERSION, "1.3")
        self.assertEqual(server.app.version, server.APP_VERSION)

    def test_scoped_opensanctions_proxy_config(self):
        outbound = {"type": "hysteria2", "tag": "auto-9", "server": "proxy.invalid", "password": "not-printed"}
        config, firewall = build_proxy_config({"outbounds": [outbound, {"type": "direct", "tag": "direct"}]})
        self.assertEqual(config["inbounds"], [{
            "type": "socks", "tag": "fnsrus-opensanctions-in", "listen": "10.8.0.1", "listen_port": 19450,
        }])
        self.assertEqual(config["outbounds"], [outbound])
        self.assertEqual(config["route"]["final"], "auto-9")
        self.assertIn('ip saddr != 10.8.0.5 drop', firewall)
        with self.assertRaises(ValueError):
            build_proxy_config({"outbounds": [{"type": "vless", "tag": "auto-9"}]})

    def test_opensanctions_downloader_requests_compression(self):
        command = opensanctions_import.curl_command("https://example.invalid/entities.ftm.json")
        self.assertIn("--compressed", command)
        self.assertIn("--http1.1", command)
        self.assertIn("--http1.1", command)

    def test_opensanctions_company_row(self):
        entity = {
            "id": "ru-ogrn-1027700132195",
            "schema": "Company",
            "properties": {
                "innCode": ["7707083893"],
                "ogrnCode": ["1027700132195"],
                "name": ["ПОЛНОЕ НАИМЕНОВАНИЕ", "ПАО СБЕРБАНК"],
                "address": ["г. Москва, ул. Вавилова, д. 19"],
            },
        }
        self.assertEqual(company_row(entity), (
            "7707083893", "1027700132195", "ПАО СБЕРБАНК", "Москва", "ru-ogrn-1027700132195",
        ))
        entity["properties"]["innCode"] = ["123"]
        self.assertIsNone(company_row(entity))

    def test_opensanctions_database_search(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            database = create_database(database_path)
            insert_batch(database, [(
                "7707083893", "1027700132195", "ПАО Сбербанк", "Москва", "ru-ogrn-1027700132195",
            )])
            database.executescript("""
                CREATE VIRTUAL TABLE companies_fts USING fts5(
                    name, content='companies', content_rowid='rowid',
                    tokenize='unicode61 remove_diacritics 2'
                );
                INSERT INTO companies_fts(companies_fts) VALUES ('rebuild');
            """)
            database.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
                ("source", "OpenSanctions"), ("dataset", "ru_egrul"),
                ("updated_at", "2026-09-12T19:08:33"), ("last_change", "2026-08-12T19:08:31"),
                ("license", "CC BY-NC 4.0"),
                ("sync_state", "running"), ("pending_version", "20261012190838-iez"),
                ("sync_companies", "1"),
            ])
            database.commit()
            database.close()

            with patch.object(server, "OPENSANCTIONS_DB", database_path), patch.object(
                server, "invoke_egrul_search", side_effect=AssertionError("MCP fallback should not run")
            ):
                response = self.client.post("/api/search", json={"query": "сбербанк"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"], [{"name": "ПАО Сбербанк", "inn": "7707083893", "city": "Москва"}])
        self.assertFalse(payload["truncated"])
        self.assertEqual(payload["source"], "OpenSanctions")
        self.assertEqual(payload["snapshot_date"], "2026-09-12")
        self.assertEqual(payload["license"], "CC BY-NC 4.0")
        self.assertTrue(payload["partial_sync"])
        self.assertEqual(payload["sync_version"], "20261012190838-iez")
        self.assertEqual(payload["synced_companies"], "1")

    def test_opensanctions_stream_import_builds_fts_database(self):
        company = {
            "id": "ru-ogrn-1027700132195",
            "schema": "Company",
            "properties": {
                "innCode": ["7707083893"], "ogrnCode": ["1027700132195"],
                "name": ["ПАО Сбербанк"], "address": ["г. Москва, ул. Вавилова"],
            },
        }
        ignored = {"id": "person-1", "schema": "Person", "properties": {"name": ["Не компания"]}}
        payload = "\n".join(json.dumps(item, ensure_ascii=False) for item in (company, ignored)).encode() + b"\n"

        class FakeProcess:
            def __init__(self):
                self.stdout = io.BytesIO(payload)
                self.stderr = io.BytesIO()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            status_path = Path(directory) / "opensanctions-status.json"
            index = {
                "version": "20260912190833-iof", "updated_at": "2026-09-12T19:08:33",
                "last_change": "2026-08-12T19:08:31", "entity_count": 2,
                "resource_url": "https://data.opensanctions.org/artifacts/ru_egrul/20260912190833-iof/entities.ftm.json",
                "resource_size": len(payload), "resource_checksum": hashlib.sha1(payload).hexdigest(),
            }
            status_path.write_text(json.dumps({
                "state": "failed", "error": "previous run failed", "invalid_lines": 1,
            }), encoding="utf-8")
            with patch.object(opensanctions_import, "DATABASE", database_path), \
                    patch.object(opensanctions_import, "STATUS_FILE", status_path), \
                    patch.object(opensanctions_import, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_import, "STATUS_INTERVAL", 1), \
                    patch.object(opensanctions_import, "fetch_index", return_value=index), \
                    patch.object(opensanctions_import.subprocess, "Popen", return_value=FakeProcess()), \
                    patch.object(opensanctions_import, "company_row", wraps=opensanctions_import.company_row) as convert_company, \
                    patch.object(opensanctions_import, "write_status", wraps=opensanctions_import.write_status) as write_status:
                result = opensanctions_import.import_snapshot()

            self.assertTrue(database_path.exists())
            self.assertFalse(list(Path(directory).glob(".opensanctions.sqlite.*.tmp")))
            database = sqlite3.connect(database_path)
            try:
                row = database.execute("SELECT inn, name, city FROM companies").fetchone()
                match_count = database.execute(
                    "SELECT COUNT(*) FROM companies_fts WHERE companies_fts MATCH ?", ('"сбербанк"*',)
                ).fetchone()[0]
                metadata = dict(database.execute("SELECT key, value FROM metadata"))
            finally:
                database.close()

            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["imported"], 1)
            self.assertEqual(result["synced_companies"], 1)
            convert_company.assert_called_once()
            self.assertEqual(row, ("7707083893", "ПАО Сбербанк", "Москва"))
            self.assertEqual(match_count, 1)
            self.assertEqual(metadata["license"], "CC BY-NC 4.0")
            completed_status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(completed_status["state"], "complete")
            self.assertIsNone(completed_status["error"])
            self.assertEqual(completed_status["invalid_lines"], 0)
            write_status.assert_any_call(
                state="running", version=index["version"], attempt=1, max_attempts=8,
                imported=1, synced_companies=1, scanned=1, invalid_lines=0, error=None,
            )

    def test_opensanctions_stream_import_rejects_incomplete_data(self):
        company = {
            "id": "ru-ogrn-1027700132195",
            "schema": "Company",
            "properties": {"innCode": ["7707083893"], "ogrnCode": ["1027700132195"], "name": ["ПАО Сбербанк"]},
        }
        valid_line = json.dumps(company, ensure_ascii=False).encode() + b"\n"

        class FakeProcess:
            def __init__(self, payload):
                self.stdout = io.BytesIO(payload)
                self.stderr = io.BytesIO()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        malformed_company_line = b'{"id":"bad","schema":"Company",bad-json}\n'
        scenarios = (
            (valid_line, 2, None, "FTM stream неполный"),
            (valid_line + malformed_company_line, 2, None, "некорректные строки"),
            (valid_line, 1, "0" * 40, "SHA-1 FTM stream не совпал"),
        )
        for payload, expected_entities, checksum, expected_error in scenarios:
            with self.subTest(expected_error=expected_error), tempfile.TemporaryDirectory() as directory:
                database_path = Path(directory) / "opensanctions.sqlite"
                status_path = Path(directory) / "opensanctions-import-status.json"
                index = {
                    "version": "20260912190833-iof", "updated_at": "2026-09-12T19:08:33",
                    "last_change": "2026-08-12T19:08:31", "entity_count": expected_entities,
                    "resource_url": "https://data.opensanctions.org/artifacts/ru_egrul/20260912190833-iof/entities.ftm.json",
                    "resource_size": len(payload),
                    "resource_checksum": checksum or hashlib.sha1(payload).hexdigest(),
                }
                with patch.object(opensanctions_import, "DATABASE", database_path), \
                        patch.object(opensanctions_import, "STATUS_FILE", status_path), \
                        patch.object(opensanctions_import, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_import, "MAX_DOWNLOAD_ATTEMPTS", 1), \
                    patch.object(opensanctions_import, "RETRY_BACKOFF_SECONDS", (0,)), \
                        patch.object(opensanctions_import, "fetch_index", return_value=index), \
                        patch.object(opensanctions_import.subprocess, "Popen", return_value=FakeProcess(payload)):
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        opensanctions_import.import_snapshot()
                self.assertTrue(database_path.exists())
                database = sqlite3.connect(database_path)
                try:
                    self.assertEqual(database.execute("SELECT COUNT(*) FROM companies").fetchone()[0], 1)
                finally:
                    database.close()
                status = json.loads(status_path.read_text(encoding="utf-8"))
                expected_state = "interrupted" if expected_error.startswith("SHA-1") else "failed"
                self.assertEqual(status["state"], expected_state)
                self.assertEqual(status["synced_companies"], 1)

    def test_opensanctions_import_rejects_changed_expected_version_before_download(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            status_path = Path(directory) / "import-status.json"
            index = {
                "version": "20261014190000-new", "entity_count": 1,
                "updated_at": "2026-10-14T19:00:00+00:00", "last_change": "2026-10-14T18:00:00+00:00",
                "resource_url": "https://data.opensanctions.org/artifacts/ru_egrul/20261014190000-new/entities.ftm.json",
                "resource_size": 0, "resource_checksum": "0" * 40,
            }
            with patch.object(opensanctions_import, "DATABASE", database_path), \
                    patch.object(opensanctions_import, "STATUS_FILE", status_path), \
                    patch.object(opensanctions_import, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_import, "fetch_index", return_value=index), \
                    patch.object(opensanctions_import.subprocess, "Popen") as process:
                with self.assertRaisesRegex(RuntimeError, "snapshot changed"):
                    opensanctions_import.import_snapshot("20261014180000-old")
            self.assertEqual(json.loads(status_path.read_text(encoding="utf-8"))["state"], "failed")
            process.assert_not_called()
            self.assertEqual(list(Path(directory).glob(".opensanctions*.tmp")), [])

    def test_opensanctions_import_keeps_live_batches_and_resumes_after_disconnect(self):
        company_one = {
            "id": "entity-1", "schema": "Company",
            "properties": {"innCode": ["7707083893"], "name": ["ПАО Сбербанк"]},
        }
        company_two = {
            "id": "entity-2", "schema": "Company",
            "properties": {"innCode": ["7812014560"], "name": ["ПАО Газпром"]},
        }
        first_line = json.dumps(company_one, ensure_ascii=False).encode() + b"\n"
        complete_payload = first_line + json.dumps(company_two, ensure_ascii=False).encode() + b"\n"

        class FakeProcess:
            def __init__(self, payload, return_code=0):
                self.stdout = io.BytesIO(payload)
                self.stderr = io.BytesIO(b"curl: (18) transfer closed with outstanding read data remaining")
                self.return_code = return_code

            def poll(self):
                return self.return_code

            def wait(self, timeout=None):
                return self.return_code

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            status_path = Path(directory) / "status.json"
            old_version = "20260912190833-iof"
            old_database = opensanctions_import.ensure_live_database(database_path)
            try:
                insert_batch(old_database, [("7801000000", None, "Старая компания", "Москва", "old-entity")], old_version)
                opensanctions_import.update_metadata(old_database, {
                    "version": old_version, "source": "OpenSanctions", "dataset": "ru_egrul",
                    "updated_at": "2026-09-12T19:08:33+00:00", "last_change": "2026-08-12T19:08:31+00:00",
                    "sync_state": "complete", "companies": "1",
                })
            finally:
                old_database.close()
            index = {
                "version": "20261012190838-iez", "updated_at": "2026-10-12T19:08:38+00:00",
                "last_change": "2026-08-12T19:08:31+00:00", "entity_count": 2,
                "resource_url": "https://data.opensanctions.org/artifacts/ru_egrul/20261012190838-iez/entities.ftm.json",
                "resource_size": len(complete_payload), "resource_checksum": hashlib.sha1(complete_payload).hexdigest(),
            }
            shared_patches = (
                patch.object(opensanctions_import, "DATABASE", database_path),
                patch.object(opensanctions_import, "STATUS_FILE", status_path),
                patch.object(opensanctions_import, "MIN_FREE_BYTES", 0),
                patch.object(opensanctions_import, "BATCH_SIZE", 100_000),
                patch.object(opensanctions_import, "STATUS_INTERVAL", 1),
                patch.object(opensanctions_import, "MAX_DOWNLOAD_ATTEMPTS", 1),
                patch.object(opensanctions_import, "RETRY_BACKOFF_SECONDS", (0,)),
                patch.object(opensanctions_import, "fetch_index", return_value=index),
            )
            with shared_patches[0], shared_patches[1], shared_patches[2], shared_patches[3], \
                    shared_patches[4], shared_patches[5], shared_patches[6], shared_patches[7]:
                with patch.object(opensanctions_import.subprocess, "Popen", return_value=FakeProcess(first_line, 18)):
                    with self.assertRaises(RuntimeError):
                        opensanctions_import.import_snapshot(index["version"])

                self.assertTrue(database_path.exists())
                database = sqlite3.connect(database_path)
                try:
                    partial_rows = database.execute("SELECT inn FROM companies ORDER BY inn").fetchall()
                    metadata = dict(database.execute("SELECT key, value FROM metadata"))
                finally:
                    database.close()
                self.assertEqual(partial_rows, [("7707083893",), ("7801000000",)])
                self.assertEqual(metadata["version"], old_version)
                self.assertEqual(metadata["sync_state"], "interrupted")
                self.assertEqual(json.loads(status_path.read_text(encoding="utf-8"))["state"], "interrupted")

                with patch.object(opensanctions_import.subprocess, "Popen", return_value=FakeProcess(complete_payload)):
                    result = opensanctions_import.import_snapshot(index["version"])

            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["synced_companies"], 2)
            database = sqlite3.connect(database_path)
            try:
                rows = database.execute("SELECT inn FROM companies ORDER BY inn").fetchall()
                match_count = database.execute(
                    "SELECT COUNT(*) FROM companies_fts WHERE companies_fts MATCH ?", ('"газпром"*',)
                ).fetchone()[0]
                old_match_count = database.execute(
                    "SELECT COUNT(*) FROM companies_fts WHERE companies_fts MATCH ?", ('"старая"*',)
                ).fetchone()[0]
                metadata = dict(database.execute("SELECT key, value FROM metadata"))
            finally:
                database.close()
            self.assertEqual(rows, [("7707083893",), ("7812014560",)])
            self.assertEqual(match_count, 1)
            self.assertEqual(old_match_count, 0)
            self.assertEqual(metadata["version"], index["version"])

    def test_opensanctions_import_commits_live_batch_before_stream_finishes(self):
        entities = [
            {"id": "entity-1", "schema": "Company", "properties": {"innCode": ["7707083893"], "name": ["ПАО Сбербанк"]}},
            {"id": "entity-2", "schema": "Company", "properties": {"innCode": ["7812014560"], "name": ["ПАО Газпром"]}},
        ]
        lines = [json.dumps(entity, ensure_ascii=False).encode() + b"\n" for entity in entities]
        payload = b"".join(lines)

        class LiveCheckingStream:
            def __init__(self, database_path):
                self.database_path = database_path
                self.batch_visible_before_end = False

            def __iter__(self):
                yield lines[0]
                reader = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True)
                try:
                    self.batch_visible_before_end = reader.execute(
                        "SELECT COUNT(*) FROM companies WHERE inn = ?", ("7707083893",)
                    ).fetchone()[0] == 1
                finally:
                    reader.close()
                yield lines[1]

        class FakeProcess:
            def __init__(self, stream):
                self.stdout = stream
                self.stderr = io.BytesIO()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            status_path = Path(directory) / "status.json"
            version = "20261012190838-iez"
            index = {
                "version": version, "updated_at": "2026-10-12T19:08:38+00:00",
                "last_change": "2026-08-12T19:08:31+00:00", "entity_count": 2,
                "resource_url": f"https://data.opensanctions.org/artifacts/ru_egrul/{version}/entities.ftm.json",
                "resource_size": len(payload), "resource_checksum": hashlib.sha1(payload).hexdigest(),
            }
            stream = LiveCheckingStream(database_path)
            with patch.object(opensanctions_import, "DATABASE", database_path), \
                    patch.object(opensanctions_import, "STATUS_FILE", status_path), \
                    patch.object(opensanctions_import, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_import, "BATCH_SIZE", 1), \
                    patch.object(opensanctions_import, "STATUS_INTERVAL", 100_000), \
                    patch.object(opensanctions_import, "fetch_index", return_value=index), \
                    patch.object(opensanctions_import.subprocess, "Popen", return_value=FakeProcess(stream)):
                result = opensanctions_import.import_snapshot(version)

            self.assertTrue(stream.batch_visible_before_end)
            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["synced_companies"], 2)

    def test_opensanctions_archive_preflight_accounts_for_archive_and_postgres_reserve(self):
        index = {"version": "20261012190838-iez", "resource_size": 1000, "resource_checksum": "a" * 40}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(opensanctions_archive.shutil, "disk_usage", return_value=SimpleNamespace(free=9_000)):
            archive_dir = Path(directory) if os.name == "nt" else Path("/var/lib/mcp-fns/archive-preflight-test")
            plan = opensanctions_archive.archive_preflight(
                index, archive_dir, postgres_reserve_bytes=2_000,
            )
        self.assertEqual(plan["archive_size_bytes"], 1000)
        self.assertEqual(plan["required_free_bytes"], 1000 + opensanctions_archive.MIN_FREE_BYTES + 2000)
        self.assertFalse(plan["space_sufficient"])

    def test_opensanctions_archive_preflight_reports_postgres_readiness_and_space(self):
        version = "20261012190838-iez"
        index = {
            "version": version, "entity_count": 100,
            "updated_at": "2026-10-12T19:08:38+00:00", "last_change": "2026-08-12T19:08:31+00:00",
            "resource_size": 1000, "resource_checksum": "a" * 40,
        }
        plan = {
            "archive_path": "/var/lib/mcp-fns/archives/archive.jsonl", "archive_size_bytes": 1000,
            "available_bytes": 9000, "required_free_bytes": 8000, "space_sufficient": True,
        }
        with patch.object(server, "OPENSANCTIONS_POSTGRES_DSN", "configured"), \
                patch.object(server.opensanctions_postgres_import, "check_postgres", return_value={
                    "configured": True, "ready": False, "error": "connection_failed",
                }), \
                patch.object(opensanctions_import, "fetch_index", return_value=index), \
                patch.object(opensanctions_archive, "probe_range", return_value=False), \
                patch.object(opensanctions_archive, "archive_preflight", return_value=plan):
            response = self.client.get(
                f"/api/settings/opensanctions/archive/preflight?expected_version={version}",
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available_bytes"], 9000)
        self.assertFalse(response.json()["postgres_ready"])
        self.assertFalse(response.json()["can_start"])
        self.assertEqual(response.json()["download_mode"], "single-stream")

    def test_opensanctions_archive_start_refuses_unavailable_postgres(self):
        version = "20261012190838-iez"
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(server, "OPENSANCTIONS_POSTGRES_DSN", "configured"), \
                patch.object(server.opensanctions_postgres_import, "check_postgres", return_value={
                    "configured": True, "ready": False, "error": "connection_failed",
                }), \
                patch.object(opensanctions_import, "fetch_index") as fetch_index:
            response = self.client.post(
                "/api/settings/opensanctions/archive/start", headers=headers,
                json={"expected_version": version},
            )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "postgres_unavailable")
        fetch_index.assert_not_called()

    def test_opensanctions_archive_start_launches_checked_single_stream(self):
        version = "20261012190838-iez"
        index = {
            "version": version, "entity_count": 2,
            "updated_at": "2026-10-12T19:08:38+00:00", "last_change": "2026-08-12T19:08:31+00:00",
            "resource_size": 1000, "resource_checksum": "a" * 40,
        }
        plan = {
            "available_bytes": 9000, "required_free_bytes": 8000, "space_sufficient": True,
        }
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(server, "OPENSANCTIONS_POSTGRES_DSN", "configured"), \
                patch.object(server.opensanctions_postgres_import, "check_postgres", return_value={
                    "configured": True, "ready": True, "error": None,
                }), \
                patch.object(opensanctions_import, "fetch_index", return_value=index), \
                patch.object(opensanctions_archive, "probe_range", return_value=False), \
                patch.object(opensanctions_archive, "archive_preflight", return_value=plan), \
                patch.object(server, "import_control", side_effect=[
                    {"ok": True, "active": False},
                    {"ok": True, "active": True,
                     "unit": f"fnsrus-opensanctions-archive@{version}.service"},
                ]) as control:
            response = self.client.post(
                "/api/settings/opensanctions/archive/start", headers=headers,
                json={"expected_version": version},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["download_mode"], "single-stream")
        self.assertEqual(response.json()["workers"], 1)
        self.assertEqual(control.call_args_list[1].args, ("archive_start", version))

    def test_opensanctions_archive_single_stream_requests_identity_encoding(self):
        command = opensanctions_archive.archive_curl_command(
            "https://data.opensanctions.org/artifacts/ru_egrul/snapshot/entities.ftm.json",
        )
        self.assertNotIn("--compressed", command)
        self.assertEqual(command[command.index("--header") + 1], "Accept-Encoding: identity")

    def test_opensanctions_archive_parallel_segments_assemble_and_manifest_resume(self):
        payload = bytes(range(64))
        version = "20261012190838-iez"
        index = {
            "version": version, "resource_size": len(payload),
            "resource_checksum": hashlib.sha1(payload).hexdigest(),
            "resource_url": f"https://data.opensanctions.org/artifacts/ru_egrul/{version}/entities.ftm.json",
        }

        def fake_range(url, start, end, total_size, descriptor, cancel=None):
            chunk = payload[start:end + 1]
            opensanctions_archive._write_at(descriptor, chunk, start)
            return len(chunk)

        with tempfile.TemporaryDirectory() as directory:
            archive_dir = Path(directory) / "archive"
            status_path = Path(directory) / "archive-status.json"
            with patch.object(opensanctions_archive, "CHUNK_SIZE", 16), \
                    patch.object(opensanctions_archive, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_archive, "POSTGRES_RESERVE_BYTES", 0), \
                    patch.object(opensanctions_archive, "probe_range", return_value=True), \
                    patch.object(opensanctions_archive, "_curl_range", side_effect=fake_range):
                result = opensanctions_archive.download_archive(index, archive_dir, status_path, workers=2)
            archive = Path(result["archive_path"])
            self.assertTrue(archive.is_file())
            self.assertEqual(archive.read_bytes(), payload)
            self.assertFalse(list(archive_dir.glob("*.manifest.json")))
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "downloaded")
            self.assertTrue(status["range_supported"])

    def test_opensanctions_archive_falls_back_when_range_is_ignored(self):
        index = {
            "version": "20261012190838-iez", "resource_size": 100,
            "resource_checksum": "a" * 40,
        }
        result = {"archive_path": "/configured/archive.jsonl", "range_supported": False,
                  "download_mode": "single-stream"}
        with tempfile.TemporaryDirectory() as directory:
            archive_dir = Path(directory) / "archive"
            archive_dir.mkdir()
            _, partial, manifest = opensanctions_archive.archive_paths(index["version"], archive_dir)
            partial.write_bytes(b"stale partial")
            manifest.write_text(json.dumps({
                "version": index["version"], "size": index["resource_size"],
                "checksum": index["resource_checksum"], "chunk_size": opensanctions_archive.CHUNK_SIZE,
                "completed": [0],
            }), encoding="utf-8")
            with patch.object(opensanctions_archive, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_archive, "POSTGRES_RESERVE_BYTES", 0), \
                    patch.object(opensanctions_archive, "probe_range", return_value=False), \
                    patch.object(opensanctions_archive, "download_single_stream", return_value=result) as fallback:
                actual = opensanctions_archive.download_archive(
                    index, archive_dir, Path(directory) / "status.json",
                )
        self.assertEqual(actual["download_mode"], "single-stream")
        self.assertFalse(manifest.exists())
        fallback.assert_called_once()

    def test_opensanctions_archive_falls_back_if_segment_range_is_ignored(self):
        payload = bytes(range(64))
        version = "20261012190838-iez"
        index = {
            "version": version, "resource_size": len(payload),
            "resource_checksum": hashlib.sha1(payload).hexdigest(),
            "resource_url": f"https://data.opensanctions.org/artifacts/ru_egrul/{version}/entities.ftm.json",
        }
        result = {"archive_path": "/configured/archive.jsonl", "range_supported": False,
                  "download_mode": "single-stream"}

        def ignored_range(*_args, **_kwargs):
            raise opensanctions_archive.RangeUnsupportedError("CDN returned HTTP 200")

        with tempfile.TemporaryDirectory() as directory:
            archive_dir = Path(directory) / "archive"
            archive_dir.mkdir()
            archive, partial, manifest = opensanctions_archive.archive_paths(version, archive_dir)
            partial.write_bytes(b"stale partial")
            manifest.write_text(json.dumps({
                "version": version, "size": len(payload), "checksum": index["resource_checksum"],
                "chunk_size": 16, "completed": [0],
            }), encoding="utf-8")
            with patch.object(opensanctions_archive, "CHUNK_SIZE", 16), \
                    patch.object(opensanctions_archive, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_archive, "POSTGRES_RESERVE_BYTES", 0), \
                    patch.object(opensanctions_archive, "probe_range", return_value=True), \
                    patch.object(opensanctions_archive, "_curl_range", side_effect=ignored_range), \
                    patch.object(opensanctions_archive, "download_single_stream", return_value=result) as fallback:
                actual = opensanctions_archive.download_archive(
                    index, archive_dir, Path(directory) / "status.json", workers=2,
                )
        self.assertEqual(actual["download_mode"], "single-stream")
        self.assertFalse(partial.exists())
        self.assertFalse(manifest.exists())
        fallback.assert_called_once_with(index, archive, partial, Path(directory) / "status.json")

    def test_opensanctions_postgres_copy_batch_deduplicates_inn(self):
        class FakeCopy:
            def __init__(self):
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def write_row(self, row):
                self.rows.append(row)

        class FakeCursor:
            rowcount = 2

            def __init__(self):
                self.copy_stream = FakeCopy()

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def copy(self, query):
                self.copy_query = query
                return self.copy_stream

            def execute(self, query):
                self.upsert_query = query

        cursor = FakeCursor()

        class FakeConnection:
            def transaction(self):
                return nullcontext()

            def cursor(self):
                return cursor

        rows = [
            ("7707083893", "1027700132195", "Old name", "Москва", "entity-old"),
            ("7707083893", "1027700132195", "New name", "Москва", "entity-new"),
        ]
        changed = opensanctions_postgres_import.sync_batch(FakeConnection(), rows, "20261012190838-iez")
        self.assertEqual(changed, 2)
        self.assertEqual(cursor.copy_stream.rows, [(*row, "20261012190838-iez") for row in rows])
        self.assertIn("DISTINCT ON (inn)", cursor.upsert_query)
        self.assertIn("ORDER BY inn, sequence_id DESC", cursor.upsert_query)

    def test_opensanctions_postgres_import_verifies_then_publishes(self):
        version = "20261012190838-iez"
        entities = [
            {"id": "entity-old", "schema": "Company", "properties": {
                "innCode": ["7707083893"], "ogrnCode": ["1027700132195"],
                "name": ["Old name"], "address": ["г. Москва"],
            }},
            {"id": "entity-new", "schema": "Company", "properties": {
                "innCode": ["7707083893"], "ogrnCode": ["1027700132195"],
                "name": ["New name"], "address": ["г. Москва"],
            }},
        ]
        payload = b"".join(json.dumps(entity, ensure_ascii=False).encode("utf-8") + b"\n" for entity in entities)
        state = {
            "companies": {"old-inn": ("old-inn", None, "Old company", "Москва", "old-entity", "old-version")},
            "metadata": {},
            "batch_rows": [],
            "sequence": 0,
            "changed": 0,
        }

        class FakeCopy:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def write_row(self, row):
                state["sequence"] += 1
                state["batch_rows"].append((state["sequence"], *row))

        class FakeCursor:
            def __init__(self):
                self.rowcount = 0
                self.result = None

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def copy(self, _query):
                return FakeCopy()

            def execute(self, query, parameters=None):
                normalized = " ".join(query.split())
                if normalized.startswith("SELECT COUNT(*)"):
                    target_version = parameters[0]
                    self.result = (sum(row[5] == target_version for row in state["companies"].values()),)
                elif normalized.startswith(f"INSERT INTO {opensanctions_postgres_import.COMPANY_TABLE}("):
                    latest_by_inn = {}
                    for sequence, *row in state["batch_rows"]:
                        latest_by_inn[row[0]] = (sequence, row)
                    self.rowcount = 0
                    for _, row in latest_by_inn.values():
                        if state["companies"].get(row[0]) != row:
                            self.rowcount += 1
                        state["companies"][row[0]] = row
                    state["batch_rows"].clear()
                    state["changed"] += self.rowcount
                elif normalized.startswith(f"DELETE FROM {opensanctions_postgres_import.COMPANY_TABLE}"):
                    target_version = parameters[0]
                    state["companies"] = {
                        inn: row for inn, row in state["companies"].items() if row[5] == target_version
                    }

            def executemany(self, query, rows):
                if opensanctions_postgres_import.META_TABLE in query:
                    state["metadata"].update(dict(rows))

            def fetchone(self):
                return self.result

        class FakeConnection:
            autocommit = True

            def transaction(self):
                return nullcontext()

            def cursor(self):
                return FakeCursor()

            def rollback(self):
                pass

            def close(self):
                state["closed"] = True

        connection = FakeConnection()
        fake_driver = SimpleNamespace(connect=lambda _dsn, connect_timeout: connection)
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "archive.jsonl"
            status_path = Path(directory) / "archive-status.json"
            archive_path.write_bytes(payload)
            status_path.write_text(json.dumps({
                "archive_size_bytes": len(payload),
                "archive_checksum": hashlib.sha1(payload).hexdigest(),
                "expected_entities": len(entities),
                "source_updated_at": "2026-10-12T19:08:38+00:00",
                "last_source_change": "2026-08-12T19:08:31+00:00",
            }), encoding="utf-8")
            with patch.dict(sys.modules, {"psycopg": fake_driver}), \
                    patch.object(opensanctions_postgres_import, "BATCH_SIZE", 1), \
                    patch.object(opensanctions_postgres_import.shutil, "disk_usage",
                                 return_value=SimpleNamespace(free=opensanctions_postgres_import.MIN_FREE_BYTES + 1)):
                result = opensanctions_postgres_import.import_archive(
                    archive_path, version, dsn="postgresql://test", status_file=status_path,
                )
            status = json.loads(status_path.read_text(encoding="utf-8"))

        self.assertEqual(result["state"], "complete")
        self.assertEqual(result["scanned"], 2)
        self.assertEqual(result["synced_companies"], 1)
        self.assertEqual(state["companies"]["7707083893"][2], "New name")
        self.assertEqual(state["companies"]["7707083893"][5], version)
        self.assertEqual(state["metadata"]["sync_state"], "complete")
        self.assertEqual(status["postgres_state"], "complete")
        self.assertTrue(state["closed"])

    def test_opensanctions_postgres_import_preserves_free_space_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(opensanctions_postgres_import.PostgresImportError):
                with patch.object(
                    opensanctions_postgres_import.shutil, "disk_usage",
                    return_value=SimpleNamespace(free=opensanctions_postgres_import.MIN_FREE_BYTES - 1),
                ):
                    opensanctions_postgres_import.ensure_import_space(Path(directory))

    def test_opensanctions_import_stop_signal_preserves_committed_batches(self):
        company = {
            "id": "entity-1", "schema": "Company",
            "properties": {"innCode": ["7707083893"], "name": ["ПАО Сбербанк"]},
        }
        line = json.dumps(company, ensure_ascii=False).encode() + b"\n"

        class StopStream:
            def __iter__(self):
                yield line
                raise opensanctions_import.ImportStopRequested("manual stop")

        class FakeProcess:
            stdout = StopStream()
            stderr = io.BytesIO()

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            status_path = Path(directory) / "status.json"
            version = "20261012190838-iez"
            index = {
                "version": version, "updated_at": "2026-10-12T19:08:38+00:00",
                "last_change": "2026-08-12T19:08:31+00:00", "entity_count": 1,
                "resource_url": f"https://data.opensanctions.org/artifacts/ru_egrul/{version}/entities.ftm.json",
                "resource_size": len(line), "resource_checksum": hashlib.sha1(line).hexdigest(),
            }
            with patch.object(opensanctions_import, "DATABASE", database_path), \
                    patch.object(opensanctions_import, "STATUS_FILE", status_path), \
                    patch.object(opensanctions_import, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_import, "BATCH_SIZE", 1), \
                    patch.object(opensanctions_import, "fetch_index", return_value=index), \
                    patch.object(opensanctions_import.subprocess, "Popen", return_value=FakeProcess()):
                with self.assertRaises(opensanctions_import.ImportStopRequested):
                    opensanctions_import.import_snapshot(version)
            status = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "interrupted")
            self.assertEqual(status["synced_companies"], 1)
            database = sqlite3.connect(database_path)
            try:
                self.assertEqual(database.execute("SELECT COUNT(*) FROM companies").fetchone()[0], 1)
                metadata = dict(database.execute("SELECT key, value FROM metadata"))
            finally:
                database.close()
            self.assertEqual(metadata["sync_state"], "interrupted")

    def test_opensanctions_import_retries_disconnect_with_idempotent_replay(self):
        first_company = {
            "id": "entity-1", "schema": "Company",
            "properties": {"innCode": ["7707083893"], "name": ["ПАО Сбербанк"]},
        }
        second_company = {
            "id": "entity-2", "schema": "Company",
            "properties": {"innCode": ["7812014560"], "name": ["ПАО Газпром"]},
        }
        first_line = json.dumps(first_company, ensure_ascii=False).encode() + b"\n"
        complete_payload = first_line + json.dumps(second_company, ensure_ascii=False).encode() + b"\n"

        class FakeProcess:
            def __init__(self, payload, return_code=0, stderr=b""):
                self.stdout = io.BytesIO(payload)
                self.stderr = io.BytesIO(stderr)
                self.return_code = return_code

            def poll(self):
                return self.return_code

            def wait(self, timeout=None):
                return self.return_code

        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "opensanctions.sqlite"
            status_path = Path(directory) / "status.json"
            version = "20261012190838-iez"
            index = {
                "version": version, "updated_at": "2026-10-12T19:08:38+00:00",
                "last_change": "2026-08-12T19:08:31+00:00", "entity_count": 2,
                "resource_url": f"https://data.opensanctions.org/artifacts/ru_egrul/{version}/entities.ftm.json",
                "resource_size": len(complete_payload),
                "resource_checksum": hashlib.sha1(complete_payload).hexdigest(),
            }
            with patch.object(opensanctions_import, "DATABASE", database_path), \
                    patch.object(opensanctions_import, "STATUS_FILE", status_path), \
                    patch.object(opensanctions_import, "MIN_FREE_BYTES", 0), \
                    patch.object(opensanctions_import, "BATCH_SIZE", 1), \
                    patch.object(opensanctions_import, "STATUS_INTERVAL", 1), \
                    patch.object(opensanctions_import, "MAX_DOWNLOAD_ATTEMPTS", 2), \
                    patch.object(opensanctions_import, "RETRY_BACKOFF_SECONDS", (0,)), \
                    patch.object(opensanctions_import, "fetch_index", return_value=index), \
                    patch.object(opensanctions_import, "time") as fake_time, \
                    patch.object(opensanctions_import.subprocess, "Popen", side_effect=[
                        FakeProcess(first_line, 18, b"curl: (18) transfer closed"),
                        FakeProcess(complete_payload),
                    ]) as popen:
                fake_time.sleep = lambda seconds: None
                result = opensanctions_import.import_snapshot(version)

            self.assertEqual(popen.call_count, 2)
            self.assertEqual(result["state"], "complete")
            self.assertEqual(result["attempt"], 2)
            self.assertEqual(result["synced_companies"], 2)
            database = sqlite3.connect(database_path)
            try:
                rows = database.execute("SELECT inn FROM companies ORDER BY inn").fetchall()
                count = database.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
            finally:
                database.close()
            self.assertEqual(rows, [("7707083893",), ("7812014560",)])
            self.assertEqual(count, 2)

    def test_opensanctions_settings_reports_average_eta(self):
        status_path = server.OPENSANCTIONS_STATUS_PATH
        status = {
            "state": "running", "version": "20260912190833-iof", "started_at": "2026-10-14T12:00:00+00:00",
            "scanned": 100, "expected_entities": 1000, "imported": 1,
            "updated_at": "2026-10-14T12:00:00+00:00", "invalid_lines": 0,
        }
        status_path.write_text(json.dumps(status), encoding="utf-8")
        with patch.object(server, "import_control", return_value={"ok": True, "active": True}):
            first = self.client.get("/api/settings/opensanctions").json()
        self.assertEqual(first["progress_percent"], 10.0)
        self.assertIsNone(first["average_rate_per_second"])
        self.assertFalse(first["can_publish"])

        status.update(scanned=400, updated_at="2026-10-14T12:01:00+00:00")
        status_path.write_text(json.dumps(status), encoding="utf-8")
        with patch.object(server, "import_control", return_value={"ok": True, "active": True}):
            second = self.client.get("/api/settings/opensanctions").json()
        self.assertEqual(second["average_rate_per_second"], 5.0)
        self.assertEqual(second["eta_seconds"], 120)

    def test_opensanctions_settings_reports_clean_starting_state(self):
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({
            "state": "complete", "version": "20260912190833-iof", "scanned": 53107328, "imported": 1042,
        }), encoding="utf-8")
        with patch.object(server, "import_control", return_value={
            "ok": True, "active": True, "expected_version": "20261014190000-new",
        }):
            response = self.client.get("/api/settings/opensanctions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "starting")
        self.assertEqual(response.json()["version"], "20261014190000-new")
        self.assertEqual(response.json()["scanned"], 0)
        self.assertEqual(response.json()["imported"], 0)
        self.assertFalse(response.json()["can_start_import"])

    def test_opensanctions_settings_hides_previous_error_during_new_run(self):
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({
            "state": "running", "version": "20261012190838-iez", "scanned": 0,
            "imported": 0, "invalid_lines": 1, "error": "previous HTTP/2 failure",
        }), encoding="utf-8")
        with patch.object(server, "import_control", return_value={"ok": True, "active": True}):
            response = self.client.get("/api/settings/opensanctions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "running")
        self.assertEqual(response.json()["invalid_lines"], 0)
        self.assertIsNone(response.json()["error"])

    def test_opensanctions_update_check_compares_published_version(self):
        current_version = "20260912190833-iof"
        latest_version = "20261014190000-new"
        database = sqlite3.connect(server.OPENSANCTIONS_DB)
        database.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.execute("INSERT INTO metadata(key, value) VALUES ('version', ?)", (current_version,))
        database.commit()
        database.close()
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "complete"}), encoding="utf-8")
        latest = {
            "version": latest_version, "entity_count": 1000,
            "updated_at": "2026-10-14T19:00:00+00:00", "last_change": "2026-10-14T18:00:00+00:00",
        }
        with patch.object(opensanctions_import, "fetch_index", return_value=latest), \
                patch.object(server, "import_control", return_value={"ok": True, "active": False}, create=True):
            response = self.client.get("/api/settings/opensanctions/update-check")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["current_version"], current_version)
        self.assertEqual(response.json()["latest_version"], latest_version)
        self.assertEqual(response.json()["decision"], "update_available")
        self.assertTrue(response.json()["can_start"])

    def test_opensanctions_update_check_hides_import_when_version_is_current(self):
        version = "20261014190000-new"
        database = sqlite3.connect(server.OPENSANCTIONS_DB)
        database.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        database.execute("INSERT INTO metadata(key, value) VALUES ('version', ?)", (version,))
        database.commit()
        database.close()
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "complete"}), encoding="utf-8")
        latest = {
            "version": version, "entity_count": 1000,
            "updated_at": "2026-10-14T19:00:00+00:00", "last_change": "2026-10-14T18:00:00+00:00",
        }
        with patch.object(opensanctions_import, "fetch_index", return_value=latest):
            response = self.client.get("/api/settings/opensanctions/update-check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "up_to_date")
        self.assertFalse(response.json()["can_start"])

    def test_opensanctions_update_check_blocks_running_import_unit(self):
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "complete"}), encoding="utf-8")
        with patch.object(server, "import_control", return_value={"ok": True, "active": True}), \
                patch.object(opensanctions_import, "fetch_index") as fetch_index:
            response = self.client.get("/api/settings/opensanctions/update-check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "import_running")
        self.assertFalse(response.json()["can_start"])
        fetch_index.assert_not_called()

    def test_opensanctions_update_check_recovers_stale_running_status(self):
        version = "20261012190838-iez"
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({
            "state": "running", "version": version, "scanned": 2000000,
            "synced_companies": 135,
        }), encoding="utf-8")
        latest = {
            "version": version, "entity_count": 53107328,
            "updated_at": "2026-10-12T19:08:38+00:00", "last_change": "2026-08-12T19:08:31+00:00",
        }
        with patch.object(opensanctions_import, "fetch_index", return_value=latest), \
                patch.object(server, "import_control", return_value={"ok": True, "active": False}):
            response = self.client.get("/api/settings/opensanctions/update-check")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["decision"], "initial_import")
        self.assertTrue(response.json()["can_start"])
        status = json.loads(server.OPENSANCTIONS_STATUS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(status["state"], "interrupted")
        self.assertEqual(status["scanned"], 2000000)
        self.assertEqual(status["synced_companies"], 135)

    def test_opensanctions_import_start_rejects_stale_checked_version(self):
        latest = {
            "version": "20261014190000-new", "entity_count": 1000,
            "updated_at": "2026-10-14T19:00:00+00:00", "last_change": "2026-10-14T18:00:00+00:00",
        }
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "complete"}), encoding="utf-8")
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(opensanctions_import, "fetch_index", return_value=latest), \
                patch.object(server, "import_control", return_value={"ok": True, "active": False}) as control:
            response = self.client.post(
                "/api/settings/opensanctions/import", headers=headers,
                json={"expected_version": "20261014180000-old"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "snapshot_changed")
        self.assertEqual(response.json()["details"]["latest_version"], latest["version"])
        control.assert_called_once_with("status")

    def test_opensanctions_import_start_refuses_active_status(self):
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "running"}), encoding="utf-8")
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(opensanctions_import, "fetch_index") as fetch_index, \
            patch.object(server, "import_control", return_value={"ok": True, "active": True}):
            response = self.client.post(
                "/api/settings/opensanctions/import", headers=headers,
                json={"expected_version": "20261014190000-new"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "import_busy")
        fetch_index.assert_not_called()

    def test_opensanctions_import_start_launches_checked_version(self):
        latest = {
            "version": "20261014190000-new", "entity_count": 1000,
            "updated_at": "2026-10-14T19:00:00+00:00", "last_change": "2026-10-14T18:00:00+00:00",
        }
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "complete"}), encoding="utf-8")
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(opensanctions_import, "fetch_index", return_value=latest), \
                patch.object(server, "import_control", side_effect=[
                    {"ok": True, "active": False},
                    {"ok": True, "active": True, "unit": "fnsrus-opensanctions-import@20261014190000-new.service"},
                ]) as control:
            response = self.client.post(
                "/api/settings/opensanctions/import", headers=headers,
                json={"expected_version": latest["version"]},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["state"], "starting")
        self.assertEqual(control.call_args_list[1].args, ("start", latest["version"]))

    def test_opensanctions_import_stop_uses_active_version(self):
        version = "20261012190838-iez"
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(server, "import_control", return_value={"ok": True, "active": False}) as control:
            response = self.client.post(
                "/api/settings/opensanctions/stop", headers=headers,
                json={"expected_version": version},
            )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"state": "stopping", "version": version})
        control.assert_called_once_with("stop", version)

    def test_opensanctions_import_stop_reports_unit_already_finished(self):
        with patch.object(server, "import_control", return_value={"ok": False, "error": "import_not_active"}):
            response = self.client.post(
                "/api/settings/opensanctions/stop",
                headers={"x-fns-settings": "1", "content-type": "application/json"},
                json={"expected_version": "20261012190838-iez"},
            )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "import_not_active")

    def test_import_control_refuses_second_start_when_busy(self):
        version = "20261014190000-new"
        active_unit = f"fnsrus-opensanctions-import@{version}.service"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(fnsrus_import_control, "CONTROL_LOCK", Path(directory) / "control.lock"), \
                patch.object(fnsrus_import_control, "read_import_status", return_value={"state": "running"}), \
            patch.object(fnsrus_import_control, "active_units", return_value=[active_unit]), \
                patch.object(fnsrus_import_control, "systemctl") as systemctl:
            result = fnsrus_import_control.handle({"command": "start", "expected_version": version})
        self.assertEqual(result["error"], "import_busy")
        systemctl.assert_not_called()

    def test_import_control_archive_start_refuses_active_sqlite_import(self):
        version = "20261012190838-iez"
        active_unit = f"fnsrus-opensanctions-import@{version}.service"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(fnsrus_import_control, "CONTROL_LOCK", Path(directory) / "control.lock"), \
                patch.object(fnsrus_import_control, "active_units", return_value=[active_unit]), \
                patch.object(fnsrus_import_control, "systemctl") as systemctl:
            result = fnsrus_import_control.handle({"command": "archive_start", "expected_version": version})
        self.assertEqual(result["error"], "import_busy")
        systemctl.assert_not_called()

    def test_import_control_starts_only_version_scoped_archive_unit(self):
        version = "20261012190838-iez"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(fnsrus_import_control, "CONTROL_LOCK", Path(directory) / "control.lock"), \
                patch.object(fnsrus_import_control, "active_units", return_value=[]), \
                patch.object(fnsrus_import_control, "systemctl", return_value=SimpleNamespace(returncode=0)) as systemctl:
            result = fnsrus_import_control.handle({"command": "archive_start", "expected_version": version})
        self.assertTrue(result["ok"])
        systemctl.assert_called_once_with(
            "start", f"fnsrus-opensanctions-archive@{version}.service", timeout=30,
        )

    def test_import_control_starts_only_version_scoped_unit(self):
        version = "20261014190000-new"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(fnsrus_import_control, "CONTROL_LOCK", Path(directory) / "control.lock"), \
                patch.object(fnsrus_import_control, "read_import_status", return_value={"state": "complete"}), \
                patch.object(fnsrus_import_control, "active_units", return_value=[]), \
                patch.object(fnsrus_import_control, "systemctl", return_value=SimpleNamespace(returncode=0)) as systemctl:
            result = fnsrus_import_control.handle({"command": "start", "expected_version": version})
        self.assertTrue(result["ok"])
        systemctl.assert_called_once_with("start", f"fnsrus-opensanctions-import@{version}.service", timeout=30)

    def test_import_control_status_reports_version_scoped_unit(self):
        version = "20261014190000-new"
        unit = f"fnsrus-opensanctions-import@{version}.service"
        with patch.object(fnsrus_import_control, "read_import_status", return_value={"state": "complete"}), \
                patch.object(fnsrus_import_control, "active_units", return_value=[unit]):
            result = fnsrus_import_control.status()
        self.assertTrue(result["active"])
        self.assertEqual(result["expected_version"], version)

    def test_control_sockets_fail_closed_without_unix_socket_support(self):
        with patch.object(server, "socket", SimpleNamespace(SOCK_STREAM=1)):
            with self.assertRaises(server.APIError) as wireguard_error:
                server.wireguard_control("status")
            with self.assertRaises(server.APIError) as import_error:
                self.import_control_function("status")
        self.assertEqual(wireguard_error.exception.code, "wireguard_control_unavailable")
        self.assertEqual(import_error.exception.code, "import_control_unavailable")

    def test_import_control_stops_only_matching_active_unit(self):
        version = "20261012190838-iez"
        unit = f"fnsrus-opensanctions-import@{version}.service"
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(fnsrus_import_control, "CONTROL_LOCK", Path(directory) / "control.lock"), \
                patch.object(fnsrus_import_control, "active_units", return_value=[unit]), \
                patch.object(fnsrus_import_control, "systemctl", return_value=SimpleNamespace(returncode=0)) as systemctl:
            result = fnsrus_import_control.handle({"command": "stop", "expected_version": version})
        self.assertTrue(result["ok"])
        self.assertTrue(result["stopping"])
        systemctl.assert_called_once_with("stop", "--no-block", unit, timeout=10)

    def test_import_control_reconciles_dead_unit_to_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "status.json"
            status_path.write_text(json.dumps({
                "state": "running", "version": "20261012190838-iez", "scanned": 100000,
                "synced_companies": 25,
            }), encoding="utf-8")
            with patch.object(fnsrus_import_control, "STATUS_FILE", status_path), \
                    patch.object(fnsrus_import_control, "active_units", return_value=[]):
                result = fnsrus_import_control.status()
            status = json.loads(status_path.read_text(encoding="utf-8"))
        self.assertFalse(result["active"])
        self.assertEqual(result["state"], "interrupted")
        self.assertEqual(status["state"], "running")
        self.assertEqual(status["scanned"], 100000)
        self.assertEqual(status["synced_companies"], 25)

    def test_opensanctions_publish_endpoint_validates_and_publishes(self):
        version = "20260912190833-iof"
        database_path = server.OPENSANCTIONS_DB
        staging = database_path.with_name(f".{database_path.name}.{version}.tmp")
        connection = create_database(staging)
        insert_batch(connection, [("7707083893", "1027700132195", "ПАО Сбербанк", "Москва", "entity-1")])
        connection.execute("""
            CREATE VIRTUAL TABLE companies_fts USING fts5(
                name, content='companies', content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
        connection.execute("INSERT INTO companies_fts(companies_fts) VALUES ('rebuild')")
        connection.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", [
            ("version", version), ("companies", "1"), ("records_scanned", "1"), ("invalid_lines", "0"),
        ])
        connection.commit()
        connection.close()
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({
            "state": "ready_to_publish", "version": version, "scanned": 1,
            "expected_entities": 1, "imported": 1, "invalid_lines": 0,
        }), encoding="utf-8")

        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        status = self.client.get("/api/settings/opensanctions").json()
        self.assertTrue(status["can_publish"])
        response = self.client.post("/api/settings/opensanctions/publish", headers=headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "complete")
        self.assertTrue(database_path.is_file())
        self.assertFalse(staging.exists())
        self.assertEqual(json.loads(server.OPENSANCTIONS_STATUS_PATH.read_text(encoding="utf-8"))["state"], "complete")

    def test_opensanctions_publish_rejects_running_import(self):
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({"state": "running"}), encoding="utf-8")
        response = self.client.post(
            "/api/settings/opensanctions/publish",
            headers={"x-fns-settings": "1", "content-type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "import_not_ready")

    def test_opensanctions_publish_rejects_corrupt_staging_without_replacing_database(self):
        version = "20260912190833-iof"
        database_path = server.OPENSANCTIONS_DB
        database_path.write_bytes(b"active database")
        staging = database_path.with_name(f".{database_path.name}.{version}.tmp")
        staging.write_bytes(b"corrupt staging")
        server.OPENSANCTIONS_STATUS_PATH.write_text(json.dumps({
            "state": "ready_to_publish", "version": version, "scanned": 1,
            "expected_entities": 1, "imported": 1, "invalid_lines": 0,
        }), encoding="utf-8")

        response = self.client.post(
            "/api/settings/opensanctions/publish",
            headers={"x-fns-settings": "1", "content-type": "application/json"},
            json={},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "invalid_import_database")
        self.assertEqual(database_path.read_bytes(), b"active database")
        self.assertTrue(staging.exists())

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
        self.assertEqual(self.client.post("/api/settings/opensanctions/publish", headers=headers, json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/opensanctions/import", headers=headers, json={"expected_version": "20261014190000-new"}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/wireguard/config", headers=headers, json={"config": "[Interface]"}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/wireguard/action", headers=headers, json={"action": "enable"}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/opensanctions/stop", headers=headers, json={"expected_version": "20261014190000-new"}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/opensanctions/stop", headers=headers, json={"expected_version": "20261014190000-new"}).status_code, 403)
        headers.pop("origin")
        response = self.client.post("/api/settings/api-fns", headers=headers, json={"api_key": "short", "enabled": True})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn("short", response.text)
        self.assertEqual(self.client.post("/api/settings/api-fns", headers=headers, json={"enabled": True}).status_code, 422)
        self.assertEqual(self.client.post("/api/settings/opensanctions/publish", json={}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/opensanctions/import", json={"expected_version": "20261014190000-new"}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/opensanctions/stop", json={"expected_version": "20261014190000-new"}).status_code, 403)
        self.assertEqual(self.client.post("/api/settings/opensanctions/stop", json={"expected_version": "20261014190000-new"}).status_code, 403)

    def test_api_settings_are_restricted_to_lan(self):
        local_response = self.client.get("/api/settings/api-fns")
        self.assertEqual(local_response.status_code, 200)

        gateway_client = TestClient(server.app, client=("10.1.17.6", 12345))
        self.assertEqual(gateway_client.get("/api/settings/api-fns").status_code, 200)

        remote_client = TestClient(server.app, client=("203.0.113.45", 54321))
        requests = (
            ("GET", "/api/settings/api-fns", {}),
            ("POST", "/api/settings/api-fns", {"json": {"enabled": False}}),
            ("POST", "/api/settings/api-fns/test", {}),
            ("DELETE", "/api/settings/api-fns", {}),
            ("GET", "/api/settings/wireguard", {}),
            ("POST", "/api/settings/wireguard", {"json": {"enabled": True}}),
            ("POST", "/api/settings/wireguard/action", {"json": {"action": "enable"}}),
            ("POST", "/api/settings/wireguard/config", {"json": {"config": "[Interface]"}}),
            ("GET", "/api/settings/opensanctions", {}),
            ("GET", "/api/settings/opensanctions/update-check", {}),
            ("POST", "/api/settings/opensanctions/import", {"json": {"expected_version": "20261014190000-new"}}),
            ("POST", "/api/settings/opensanctions/stop", {"json": {"expected_version": "20261014190000-new"}}),
            ("POST", "/api/settings/opensanctions/stop", {"json": {"expected_version": "20261014190000-new"}}),
            ("POST", "/api/settings/opensanctions/publish", {"json": {}}),
        )
        for method, path, options in requests:
            response = remote_client.request(method, path, **options)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"], "local_network_only")
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_wireguard_settings_use_control_socket(self):
        status = {
            "ok": True, "configured": True, "enabled": False, "active": False,
            "handshake": False, "endpoint": "192.168.0.39:51820", "proxy": "10.8.0.1:19450",
        }
        connected = {**status, "enabled": True, "active": True, "handshake": True}
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(server, "wireguard_control", side_effect=[status, connected]) as control:
            response = self.client.get("/api/settings/wireguard")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), status)
            response = self.client.post("/api/settings/wireguard", headers=headers, json={"enabled": True})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), connected)
        self.assertEqual([item.args[0] for item in control.call_args_list], ["status", "connect"])

    def test_wireguard_action_api_separates_autostart_from_connection(self):
        saved = {"ok": True, "configured": True, "enabled": True, "active": False, "handshake": False}
        connected = {**saved, "active": True, "handshake": True}
        disconnected = {**saved, "active": False, "handshake": False}
        headers = {"x-fns-settings": "1", "content-type": "application/json"}
        with patch.object(server, "wireguard_control", side_effect=[saved, connected, disconnected]) as control:
            save_response = self.client.post(
                "/api/settings/wireguard/action", headers=headers,
                json={"action": "save", "enabled": True},
            )
            enable_response = self.client.post(
                "/api/settings/wireguard/action", headers=headers,
                json={"action": "enable"},
            )
            disable_response = self.client.post(
                "/api/settings/wireguard/action", headers=headers,
                json={"action": "disable"},
            )
        self.assertEqual([save_response.status_code, enable_response.status_code, disable_response.status_code],
                         [200, 200, 200])
        self.assertFalse(save_response.json()["active"])
        self.assertTrue(enable_response.json()["active"])
        self.assertFalse(disable_response.json()["active"])
        self.assertEqual([item.args for item in control.call_args_list], [
            ("save", True), ("enable", None), ("disable", None),
        ])

    def test_wireguard_save_requires_autostart_choice(self):
        response = self.client.post(
            "/api/settings/wireguard/action",
            headers={"x-fns-settings": "1", "content-type": "application/json"},
            json={"action": "save"},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "wireguard_autostart_required")

    def test_wireguard_save_rejects_string_autostart_value(self):
        response = self.client.post(
            "/api/settings/wireguard/action",
            headers={"x-fns-settings": "1", "content-type": "application/json"},
            json={"action": "save", "enabled": "true"},
        )
        self.assertEqual(response.status_code, 422)

    def test_wireguard_root_helper_separates_autostart_and_runtime(self):
        helper_path = Path(server.BASE_DIR) / "scripts" / "fnsrus-wg-control.py"
        helper = runpy.run_path(str(helper_path))
        helper_globals = helper["handle"].__globals__
        helper_globals["CONFIG"] = SimpleNamespace(is_file=lambda: True)
        helper_globals["status"] = lambda: {"ok": True}
        calls = []

        def systemctl(*arguments):
            calls.append(arguments)
            return 0

        helper_globals["systemctl"] = systemctl
        scenarios = (
            ("save", True, ("enable", helper["UNIT"])),
            ("save", False, ("disable", helper["UNIT"])),
            ("enable", None, ("start", helper["UNIT"])),
            ("disable", None, ("stop", helper["UNIT"])),
        )
        for command, enabled, expected in scenarios:
            self.assertTrue(helper["handle"](command, enabled)["ok"])
            self.assertEqual(calls[-1], expected)

    def test_wireguard_config_api_delegates_to_root_helper(self):
        config = "[Interface]\nAddress = 10.8.0.5/32\n"
        saved = {
            "ok": True, "configured": True, "enabled": True, "active": True,
            "handshake": True, "config_saved": True, "restart_required": True,
            "config_text": "[Interface]\nPrivateKey = __KEEP_EXISTING__\n",
        }
        with patch.object(server, "wireguard_control", return_value=saved) as control:
            response = self.client.post(
                "/api/settings/wireguard/config",
                headers={"x-fns-settings": "1", "content-type": "application/json"},
                json={"config": config},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["restart_required"])
        control.assert_called_once_with("save_config", None, config)

    def test_wireguard_root_helper_config_edit_preserves_masked_keys(self):
        helper = runpy.run_path(str(Path(server.BASE_DIR) / "scripts" / "fnsrus-wg-control.py"))
        helper_globals = helper["handle"].__globals__
        private_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        public_key = "AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI="
        preshared_key = "AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="
        original = (
            "[Interface]\nPrivateKey = " + private_key + "\nAddress = 10.8.0.5/32\nMTU = 1420\nTable = off\n\n"
            "[Peer]\nPublicKey = " + public_key + "\nPresharedKey = " + preshared_key + "\n"
            "AllowedIPs = 10.8.0.1/32\nPersistentKeepalive = 25\nEndpoint = 192.168.0.39:51820\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "fnsrus.conf"
            config_path.write_text(original, encoding="ascii")
            helper_globals["CONFIG"] = config_path
            helper_globals["systemd_state"] = lambda *_args: True
            helper_globals["systemctl"] = lambda *_args: self.fail("config save must not invoke systemctl")
            preview = helper_globals["status"]()["config_text"]
            self.assertNotIn(private_key, preview)
            self.assertNotIn(preshared_key, preview)
            self.assertIn(public_key, preview)
            self.assertEqual(preview.count(helper_globals["PRESERVE_SECRET"]), 2)
            edited = preview.replace("Endpoint = 192.168.0.39:51820", "Endpoint = 192.0.2.5:51821")
            handshake = f"peer\t{int(helper_globals['time'].time())}\n"
            with patch.object(helper_globals["subprocess"], "check_output", return_value=handshake):
                result = helper_globals["handle"]("save_config", config_text=edited)
            saved_config = config_path.read_text(encoding="ascii")
            self.assertTrue(result["config_saved"])
            self.assertTrue(result["restart_required"])
            self.assertTrue(result["active"])
            self.assertIn(f"PrivateKey = {private_key}", saved_config)
            self.assertIn(f"PresharedKey = {preshared_key}", saved_config)
            self.assertIn("Endpoint = 192.0.2.5:51821", saved_config)
            self.assertNotIn(helper_globals["PRESERVE_SECRET"], saved_config)
            if os.name != "nt":
                self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    def test_wireguard_root_helper_imports_first_config_without_starting_tunnel(self):
        helper = runpy.run_path(str(Path(server.BASE_DIR) / "scripts" / "fnsrus-wg-control.py"))
        helper_globals = helper["handle"].__globals__
        private_key = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
        public_key = "AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI="
        config = (
            f"[Interface]\nPrivateKey = {private_key}\nAddress = 10.8.0.5/32\n\n"
            f"[Peer]\nPublicKey = {public_key}\nAllowedIPs = 10.8.0.1/32\n"
            "Endpoint = 192.0.2.5:51820\nPersistentKeepalive = 25\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "fnsrus.conf"
            helper_globals["CONFIG"] = config_path
            helper_globals["systemd_state"] = lambda *_args: False
            helper_globals["systemctl"] = lambda *_args: self.fail("config import must not change runtime")
            result = helper["handle"]("save_config", config_text=config)
            self.assertTrue(result["config_saved"])
            self.assertFalse(result["configured"] is False)
            self.assertFalse(result["active"])
            self.assertFalse(result["restart_required"])
            self.assertTrue(config_path.is_file())
            if os.name != "nt":
                self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    def test_wireguard_root_helper_imports_first_config_without_starting_tunnel(self):
        helper = runpy.run_path(str(Path(server.BASE_DIR) / "scripts" / "fnsrus-wg-control.py"))
        helper_globals = helper["handle"].__globals__
        config = (
            "[Interface]\nPrivateKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
            "Address = 10.8.0.5/32\n\n[Peer]\n"
            "PublicKey = AgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgI=\n"
            "AllowedIPs = 10.8.0.1/32\nEndpoint = 192.0.2.5:51820\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "fnsrus.conf"
            helper_globals["CONFIG"] = config_path
            helper_globals["systemd_state"] = lambda *_args: False
            helper_globals["systemctl"] = lambda *_args: self.fail("config import must not change runtime")
            result = helper["handle"]("save_config", config_text=config)
            self.assertTrue(result["config_saved"])
            self.assertTrue(result["configured"])
            self.assertFalse(result["active"])
            self.assertFalse(result["restart_required"])
            self.assertTrue(config_path.is_file())
            if os.name != "nt":
                self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)

    def test_wireguard_root_helper_rejects_root_hook_directives(self):
        helper = runpy.run_path(str(Path(server.BASE_DIR) / "scripts" / "fnsrus-wg-control.py"))
        unsafe = (
            "[Interface]\nPrivateKey = __KEEP_EXISTING__\nAddress = 10.8.0.5/32\n"
            "PostUp = touch /tmp/wg-hook\n\n[Peer]\nPublicKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
            "AllowedIPs = 10.8.0.1/32\nEndpoint = 192.0.2.5:51820\n"
        )
        with self.assertRaises(helper["ConfigError"]):
            helper["parse_config"](unsafe)

    def test_wireguard_root_helper_rejects_broad_routes_and_dns(self):
        helper = runpy.run_path(str(Path(server.BASE_DIR) / "scripts" / "fnsrus-wg-control.py"))
        config = (
            "[Interface]\nPrivateKey = __KEEP_EXISTING__\nAddress = 10.8.0.5/32\n\n"
            "[Peer]\nPublicKey = AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
            "PresharedKey = __KEEP_EXISTING__\nAllowedIPs = 10.8.0.1/32\n"
            "Endpoint = 192.0.2.5:51820\n"
        )
        sections = helper["parse_config"](config)
        helper["validate_config"](sections)
        for unsafe in (
            config.replace("AllowedIPs = 10.8.0.1/32", "AllowedIPs = 0.0.0.0/0"),
            config.replace("Address = 10.8.0.5/32", "Address = 10.8.0.6/32"),
            config.replace("[Peer]", "DNS = 1.1.1.1\n\n[Peer]"),
            config.replace("AllowedIPs = 10.8.0.1/32", "AllowedIPs = 10.8.0.1/32\nTable = 100"),
        ):
            with self.subTest(config=unsafe), self.assertRaises(helper["ConfigError"]):
                helper["validate_config"](helper["parse_config"](unsafe))

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

    def test_name_input_and_search_endpoint(self):
        search_calls = []
        checked = []

        async def fake_search(arguments):
            search_calls.append(arguments)
            return {"hits": [{"name": "ПАО Сбербанк", "inn": "7707083893", "address_legal": "г. Москва, ул. Вавилова"}]}

        async def fake_check(name, arguments):
            checked.append((name, arguments))
            return {"tool": name, "arguments": arguments}

        with patch.object(server, "invoke_egrul_search", fake_search), patch.object(server, "call_tool", fake_check):
            for identifier in ("1234567890", "123456789012", "1234567890123", "123456789012345"):
                response = self.client.post("/api/check", json={"identifier": identifier})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["arguments"], {"identifier": identifier})

            response = self.client.post("/api/check", json={"identifier": "  Сбер  "})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["results"], [{"name": "ПАО Сбербанк", "inn": "7707083893", "city": "Москва"}])

            response = self.client.post("/api/search", json={"query": "  Сбер  "})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["results"][0]["inn"], "7707083893")

        self.assertEqual(len(checked), 4)
        self.assertTrue(all(name == "check_contractor" for name, _ in checked))
        self.assertEqual(search_calls, [{"query": "Сбер", "limit": 50}, {"query": "Сбер", "limit": 50}])

    def test_search_caps_results_and_extracts_city(self):
        hits = [
            {"name": f"Компания {index}", "inn": f"{index:010d}", "address_legal": "Российская Федерация, регион, адрес"}
            for index in range(51)
        ]
        hits[0]["address_legal_structured"] = {"city": "Тула"}
        hits[1]["address_legal"] = "г. Москва, ул. Вавилова, д. 1"
        hits[2]["address_legal"] = "Очень длинный адрес без выделенного города, улица и дом"
        hits[3].pop("address_legal")

        async def fake_search(arguments):
            self.assertEqual(arguments, {"query": "компания", "limit": 50})
            return {"hits": hits, "count": len(hits)}

        with patch.object(server, "invoke_egrul_search", fake_search):
            response = self.client.post("/api/search", json={"query": "компания"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 50)
        self.assertTrue(payload["truncated"])
        self.assertTrue(all(set(item) == {"name", "inn", "city"} for item in payload["results"]))
        self.assertEqual([item["city"] for item in payload["results"][:4]], [
            "Тула", "Москва", hits[2]["address_legal"][:30], "—",
        ])

    def test_search_reports_empty_database_and_unavailable_server(self):
        async def empty_database(arguments):
            raise server.APIError(503, "search_data_unavailable", server.SEARCH_DATA_UNAVAILABLE_MESSAGE)

        with patch.object(server, "invoke_egrul_search", empty_database):
            response = self.client.post("/api/search", json={"query": "сбер"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["message"], server.SEARCH_DATA_UNAVAILABLE_MESSAGE)

        async def unavailable(arguments):
            raise RuntimeError("uvx is unavailable")

        with patch.object(server, "invoke_egrul_search", unavailable):
            response = self.client.post("/api/search", json={"query": "сбер"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["message"], "Поиск по названию временно недоступен, введите ИНН")
        self.assertEqual(self.client.post("/api/search", json={"query": "я"}).status_code, 422)

    def test_search_reports_active_opensanctions_import(self):
        with tempfile.TemporaryDirectory() as directory:
            status_path = Path(directory) / "import-status.json"
            status_path.write_text(json.dumps({"state": "running", "scanned": 100000}), encoding="utf-8")

            async def empty_database(arguments):
                raise server.APIError(503, "search_data_unavailable", server.SEARCH_DATA_UNAVAILABLE_MESSAGE)

            with patch.object(server, "OPENSANCTIONS_STATUS_PATH", status_path), \
                    patch.object(server, "import_control", return_value={"ok": True, "active": True}), \
                    patch.object(server, "invoke_egrul_search", empty_database):
                response = self.client.post("/api/search", json={"query": "сбер"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"], "search_import_in_progress")
        self.assertIn("загрузка базы OpenSanctions", response.json()["message"])

    def test_seven_tools_allowed(self):
        async def fake_call(name, arguments):
            return {"tool": name, "arguments": arguments}

        with patch.object(server, "invoke_mcp", fake_call):
            for name in sorted(server.TOOL_NAMES):
                response = self.client.post(f"/api/tools/{name}", json={"inn": "7707083893"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["tool"], name)

    def test_invalid_format_and_json(self):
        for body in ({"identifier": "12345"}, {"identifier": 7707083893}, {"identifier": "7707083893", "extra": 1}):
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