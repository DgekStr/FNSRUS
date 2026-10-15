#!/usr/bin/env python3
"""Download a complete OpenSanctions FTM archive and import it into PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import scripts.import_opensanctions as importer
from scripts.import_opensanctions import write_status_file


ARCHIVE_DIR = Path(os.environ.get(
    "FNS_OPENSANCTIONS_ARCHIVE_DIR", "/var/lib/mcp-fns/archives/opensanctions",
))
STATUS_FILE = Path(os.environ.get(
    "FNS_OPENSANCTIONS_ARCHIVE_STATUS", "/var/lib/mcp-fns/opensanctions-archive-status.json",
))
POSTGRES_DSN = os.environ.get("FNS_OPENSANCTIONS_POSTGRES_DSN", "")
DOWNLOAD_WORKERS = 8
CHUNK_SIZE = 64 * 1024**2
MAX_SEGMENT_ATTEMPTS = 4
SEGMENT_BACKOFF_SECONDS = (2, 5, 15)
MAX_DOWNLOAD_ATTEMPTS = 8
DOWNLOAD_BACKOFF_SECONDS = (15, 30, 60, 120, 300, 600, 900)
MIN_FREE_BYTES = 4 * 1024**3
POSTGRES_RESERVE_BYTES = 4 * 1024**3
IO_CHUNK_SIZE = 1024**2
RETRYABLE_CURL_CODES = {7, 18, 22, 28, 52, 55, 56, 92}
CONTENT_RANGE_RE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+)", re.IGNORECASE)
HTTP_STATUS_RE = re.compile(r"__ARCHIVE_HTTP__=(\d+)")
HTTP_RANGE_RE = re.compile(r"__ARCHIVE_RANGE__=([^\r\n]*)")
_STATUS_LOCK = threading.Lock()
_FILE_WRITE_LOCK = threading.Lock()


class ArchiveDownloadError(RuntimeError):
    pass


class RangeUnsupportedError(ArchiveDownloadError):
    pass


class RetryableSegmentError(ArchiveDownloadError):
    pass


class ArchiveSpaceError(ArchiveDownloadError):
    pass


def archive_curl_command(url: str) -> list[str]:
    return [
        "/usr/bin/curl", "--fail", "--location", "--silent", "--show-error", "--http1.1",
        "--connect-timeout", "30", "--speed-time", "120", "--speed-limit", "1024",
        "--proxy", importer.PROXY, "--header", "Accept-Encoding: identity", url,
    ]


def archive_paths(version: str, archive_dir: Path = ARCHIVE_DIR) -> tuple[Path, Path, Path]:
    filename = f"ru_egrul-{version}.entities.ftm.jsonl"
    archive = archive_dir / filename
    return archive, archive.with_name(f".{filename}.part"), archive.with_name(f".{filename}.manifest.json")


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".opensanctions-archive-status-", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_archive_status(**updates) -> dict:
    with _STATUS_LOCK:
        status = load_json(STATUS_FILE)
        status.update(updates)
        status["updated_at"] = datetime.now(UTC).isoformat()
        atomic_write_json(STATUS_FILE, status)
        return status


def _existing_parent(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _load_manifest(manifest_path: Path, index: dict) -> dict:
    value = load_json(manifest_path)
    if (value.get("version") == index["version"] and
            value.get("size") == index["resource_size"] and
            value.get("checksum") == index["resource_checksum"] and
            value.get("chunk_size") == CHUNK_SIZE):
        completed = value.get("completed", [])
        if isinstance(completed, list) and all(isinstance(item, int) and item >= 0 for item in completed):
            return {"completed": sorted(set(completed))}
    return {"completed": []}


def chunk_ranges(size: int, chunk_size: int = CHUNK_SIZE):
    for number, start in enumerate(range(0, size, chunk_size)):
        yield number, start, min(size - 1, start + chunk_size - 1)


def archive_preflight(index: dict, archive_dir: Path = ARCHIVE_DIR,
                      postgres_reserve_bytes: int = POSTGRES_RESERVE_BYTES,
                      range_supported: bool | None = None) -> dict:
    archive_dir = archive_dir.expanduser().resolve()
    allowed_root = Path("/var/lib/mcp-fns").resolve()
    if os.name != "nt" and not archive_dir.is_relative_to(allowed_root):
        raise ArchiveDownloadError("Archive directory must be under /var/lib/mcp-fns")
    archive, partial, manifest_path = archive_paths(index["version"], archive_dir)
    manifest = _load_manifest(manifest_path, index)
    size = index["resource_size"]
    if archive.is_file() and archive.stat().st_size == size:
        remaining = 0
        archive_ready = True
    elif range_supported is False:
        remaining = size
        archive_ready = False
    else:
        completed = set(manifest["completed"])
        completed_bytes = sum(
            end - start + 1 for number, start, end in chunk_ranges(size, CHUNK_SIZE) if number in completed
        )
        remaining = max(0, size - completed_bytes)
        archive_ready = False
    free = shutil.disk_usage(_existing_parent(archive_dir)).free
    required = remaining + MIN_FREE_BYTES + postgres_reserve_bytes
    return {
        "archive_path": str(archive),
        "partial_path": str(partial),
        "archive_size_bytes": size,
        "available_bytes": free,
        "remaining_download_bytes": remaining,
        "postgres_reserve_bytes": postgres_reserve_bytes,
        "minimum_free_bytes": MIN_FREE_BYTES,
        "required_free_bytes": required,
        "space_sufficient": free >= required,
        "archive_ready": archive_ready,
        "parallel_workers": DOWNLOAD_WORKERS,
        "chunk_size_bytes": CHUNK_SIZE,
        "range_supported": range_supported,
    }


def _write_at(fd: int, data: bytes, offset: int) -> None:
    if hasattr(os, "pwrite"):
        written = 0
        while written < len(data):
            written += os.pwrite(fd, data[written:], offset + written)
        return
    with _FILE_WRITE_LOCK:
        os.lseek(fd, offset, os.SEEK_SET)
        view = memoryview(data)
        written = 0
        while written < len(view):
            written += os.write(fd, view[written:])


def _parse_curl_range_metadata(stderr: str) -> tuple[int | None, str]:
    status_match = HTTP_STATUS_RE.search(stderr)
    range_match = HTTP_RANGE_RE.search(stderr)
    return (int(status_match.group(1)) if status_match else None,
            range_match.group(1).strip() if range_match else "")


def _curl_range(url: str, start: int, end: int, total_size: int,
                fd: int | None, cancel: threading.Event | None = None) -> int:
    expected = end - start + 1
    command = [
        "/usr/bin/curl", "--fail", "--location", "--silent", "--show-error", "--http1.1",
        "--connect-timeout", "30", "--speed-time", "120", "--speed-limit", "1024",
        "--proxy", importer.PROXY,
        "--header", "Accept-Encoding: identity",
        "--range", f"{start}-{end}",
        "--output", "-",
        "--write-out", "%{stderr}__ARCHIVE_HTTP__=%{http_code}\n__ARCHIVE_RANGE__=%header{content-range}\n",
        url,
    ]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    received = 0
    try:
        assert process.stdout is not None
        while received < expected:
            if cancel is not None and cancel.is_set():
                raise ArchiveDownloadError("Archive download cancelled")
            data = process.stdout.read(min(IO_CHUNK_SIZE, expected - received))
            if not data:
                break
            if fd is not None:
                _write_at(fd, data, start + received)
            received += len(data)
        extra = process.stdout.read(1)
        if extra:
            process.terminate()
            process.wait(timeout=10)
            raise RangeUnsupportedError("Upstream returned more than the requested byte range")
        return_code = process.wait()
        stderr = process.stderr.read(8192).decode("utf-8", errors="replace") if process.stderr else ""
        http_status, content_range = _parse_curl_range_metadata(stderr)
        if http_status != 206:
            raise RangeUnsupportedError(f"Upstream ignored byte range (HTTP {http_status})")
        match = CONTENT_RANGE_RE.fullmatch(content_range)
        if not match or tuple(map(int, match.groups())) != (start, end, total_size):
            raise RangeUnsupportedError("Upstream Content-Range does not match requested segment")
        if return_code != 0:
            match = re.search(r"curl: \(([0-9]+)\)", stderr)
            code = int(match.group(1)) if match else None
            if code in RETRYABLE_CURL_CODES:
                raise RetryableSegmentError(f"curl ({code}): {stderr[-500:]}")
            raise ArchiveDownloadError(f"curl exited {return_code}: {stderr[-500:]}")
        if received != expected:
            raise RetryableSegmentError(f"Segment was short: expected {expected}, received {received}")
        return received
    except Exception:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stderr and process.poll() is not None:
            process.stderr.read(8192)
        raise


def probe_range(index: dict) -> bool:
    try:
        _curl_range(index["resource_url"], 0, 0, index["resource_size"], None)
        return True
    except (RangeUnsupportedError, RetryableSegmentError):
        return False


def download_single_stream(index: dict, archive: Path, partial: Path, status_file: Path) -> dict:
    archive.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        write_status_file(status_file, state="downloading", version=index["version"],
                          archive_path=str(archive), total_bytes=index["resource_size"],
                          downloaded_bytes=0, attempt=attempt, max_attempts=MAX_DOWNLOAD_ATTEMPTS,
                          workers=1, range_supported=False, download_mode="single-stream", error=None)
        process = subprocess.Popen(
            archive_curl_command(index["resource_url"]),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        digest = hashlib.sha1()
        received = 0
        last_status = 0
        try:
            assert process.stdout is not None
            with partial.open("wb") as stream:
                while True:
                    chunk = process.stdout.read(IO_CHUNK_SIZE)
                    if not chunk:
                        break
                    stream.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if received - last_status >= 64 * 1024**2:
                        stream.flush()
                        os.fsync(stream.fileno())
                        write_status_file(status_file, state="downloading", version=index["version"],
                                          archive_path=str(archive), total_bytes=index["resource_size"],
                                          downloaded_bytes=received, attempt=attempt,
                                          max_attempts=MAX_DOWNLOAD_ATTEMPTS, workers=1,
                                          range_supported=False, download_mode="single-stream", error=None)
                        last_status = received
            return_code = process.wait()
            stderr = process.stderr.read(4096).decode("utf-8", errors="replace") if process.stderr else ""
            if return_code == 0 and received == index["resource_size"] and digest.hexdigest() == index["resource_checksum"]:
                os.replace(partial, archive)
                result = {"archive_path": str(archive), "downloaded_bytes": received,
                          "version": index["version"], "range_supported": False,
                          "download_mode": "single-stream"}
                write_status_file(status_file, state="downloaded", **result)
                return result
            curl_match = re.search(r"curl: \(([0-9]+)\)", stderr)
            code = int(curl_match.group(1)) if curl_match else None
            if return_code == 0 and received == index["resource_size"]:
                raise ArchiveDownloadError("SHA-1 archive mismatch")
            reason = f"curl ({code}) {stderr[-300:]}" if code else f"curl exit {return_code}: {stderr[-300:]}"
            if code not in RETRYABLE_CURL_CODES or attempt >= MAX_DOWNLOAD_ATTEMPTS:
                raise ArchiveDownloadError(f"Single-stream archive download failed: {reason}")
            delay = DOWNLOAD_BACKOFF_SECONDS[min(attempt - 1, len(DOWNLOAD_BACKOFF_SECONDS) - 1)]
            write_status_file(status_file, state="retrying", version=index["version"],
                              archive_path=str(archive), total_bytes=index["resource_size"],
                              downloaded_bytes=received, attempt=attempt,
                              max_attempts=MAX_DOWNLOAD_ATTEMPTS, retry_in_seconds=delay,
                              workers=1, range_supported=False, download_mode="single-stream",
                              error=reason)
            time.sleep(delay)
        except Exception:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise
    raise ArchiveDownloadError("Single-stream download retry budget exhausted")


def download_archive(index: dict, archive_dir: Path = ARCHIVE_DIR,
                     status_file: Path = STATUS_FILE, workers: int = DOWNLOAD_WORKERS) -> dict:
    archive_dir = archive_dir.expanduser().resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive, partial, manifest_path = archive_paths(index["version"], archive_dir)
    if shutil.disk_usage(archive_dir).free < MIN_FREE_BYTES:
        raise ArchiveSpaceError("Меньше 4 ГБ свободно в целевой папке архива")
    if archive.is_file() and archive.stat().st_size == index["resource_size"]:
        digest = hashlib.sha1()
        with archive.open("rb") as stream:
            for block in iter(lambda: stream.read(IO_CHUNK_SIZE), b""):
                digest.update(block)
        if digest.hexdigest() == index["resource_checksum"]:
            result = {"archive_path": str(archive), "downloaded_bytes": index["resource_size"],
                      "version": index["version"], "range_supported": True, "download_mode": "verified-existing"}
            write_status_file(status_file, state="downloaded", **result)
            return result
        archive.unlink()

    manifest = _load_manifest(manifest_path, index)
    segments = list(chunk_ranges(index["resource_size"], CHUNK_SIZE))
    segment_numbers = {number for number, _, _ in segments}
    manifest["completed"] = [number for number in manifest["completed"] if number in segment_numbers]
    completed = set(manifest["completed"])

    range_supported = probe_range(index)
    completed_bytes = sum(end - start + 1 for number, start, end in segments if number in completed)
    remaining = index["resource_size"] - completed_bytes if range_supported else index["resource_size"]
    required = remaining + MIN_FREE_BYTES + POSTGRES_RESERVE_BYTES
    available = shutil.disk_usage(archive_dir).free
    if available < required:
        raise ArchiveSpaceError(
            f"Недостаточно места: свободно {available}, требуется {required} байт "
            "(докачка + 4 ГБ reserve + 4 ГБ PostgreSQL reserve)"
        )
    if not range_supported:
        manifest_path.unlink(missing_ok=True)
        write_status_file(
            status_file,
            state="downloading",
            version=index["version"],
            range_supported=False,
            download_mode="single-stream",
            parallel_workers=0,
            note="CDN игнорирует byte-range; используется один последовательный stream.",
        )
        return download_single_stream(index, archive, partial, status_file)

    atomic_write_json(manifest_path, {
        "version": index["version"], "size": index["resource_size"],
        "checksum": index["resource_checksum"], "chunk_size": CHUNK_SIZE,
        "completed": sorted(completed),
    })
    descriptor = os.open(partial, os.O_CREAT | os.O_RDWR | getattr(os, "O_BINARY", 0), 0o640)
    cancel = threading.Event()
    progress_lock = threading.Lock()
    fallback_to_single_stream = False
    try:
        os.ftruncate(descriptor, index["resource_size"])
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for number, start, end in segments:
                if number not in completed:
                    futures[executor.submit(
                        _download_segment_with_retry, index, number, start, end, descriptor, cancel,
                    )] = (number, start, end)
            try:
                for future in as_completed(futures):
                    number, start, end = futures[future]
                    future.result()
                    with progress_lock:
                        os.fsync(descriptor)
                        completed.add(number)
                        downloaded = sum(seg_end - seg_start + 1 for seg_number, seg_start, seg_end in segments
                                         if seg_number in completed)
                        atomic_write_json(manifest_path, {
                            "version": index["version"], "size": index["resource_size"],
                            "checksum": index["resource_checksum"], "chunk_size": CHUNK_SIZE,
                            "completed": sorted(completed),
                        })
                        write_status_file(status_file, state="downloading", version=index["version"],
                                          archive_path=str(archive), total_bytes=index["resource_size"],
                                          downloaded_bytes=downloaded, chunk_size=CHUNK_SIZE,
                                          chunks_complete=len(completed), chunks_total=len(segments),
                                          workers=workers, range_supported=True, error=None)
            except RangeUnsupportedError:
                cancel.set()
                for future in futures:
                    future.cancel()
                fallback_to_single_stream = True
            except Exception:
                cancel.set()
                for future in futures:
                    future.cancel()
                raise
    finally:
        os.close(descriptor)

    if fallback_to_single_stream:
        manifest_path.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        write_status_file(
            status_file,
            state="downloading",
            version=index["version"],
            range_supported=False,
            download_mode="single-stream",
            parallel_workers=0,
            note="CDN перестал поддерживать byte-range; загрузка продолжена одним потоком.",
        )
        return download_single_stream(index, archive, partial, status_file)

    digest = hashlib.sha1()
    with partial.open("rb") as stream:
        for block in iter(lambda: stream.read(IO_CHUNK_SIZE), b""):
            digest.update(block)
    if digest.hexdigest() != index["resource_checksum"]:
        manifest["completed"] = []
        atomic_write_json(manifest_path, {
            "version": index["version"], "size": index["resource_size"],
            "checksum": index["resource_checksum"], "chunk_size": CHUNK_SIZE, "completed": [],
        })
        raise ArchiveDownloadError("SHA-1 полного архива не совпал; сегменты сброшены для безопасного retry")
    os.replace(partial, archive)
    manifest_path.unlink(missing_ok=True)
    result = {"archive_path": str(archive), "downloaded_bytes": index["resource_size"],
              "range_supported": True, "version": index["version"]}
    write_status_file(status_file, state="downloaded", **result)
    return result


def _download_segment_with_retry(index, number, start, end, descriptor, cancel):
    last_error = None
    for attempt in range(1, MAX_SEGMENT_ATTEMPTS + 1):
        if cancel.is_set():
            raise ArchiveDownloadError("Archive download cancelled")
        try:
            return _curl_range(index["resource_url"], start, end, index["resource_size"], descriptor, cancel)
        except RetryableSegmentError as error:
            last_error = error
            if attempt >= MAX_SEGMENT_ATTEMPTS:
                break
            time.sleep(SEGMENT_BACKOFF_SECONDS[min(attempt - 1, len(SEGMENT_BACKOFF_SECONDS) - 1)])
    raise ArchiveDownloadError(f"Segment {number} failed after retries: {last_error}")


def run_archive_job(expected_version: str, archive_dir: Path = ARCHIVE_DIR,
                    status_file: Path = STATUS_FILE, postgres_dsn: str = POSTGRES_DSN) -> dict:
    write_status_file(status_file, state="checking", version=expected_version,
                      download_mode="checking", error=None, postgres_state="waiting")
    if not isinstance(expected_version, str) or not re.fullmatch(r"[0-9]{14}-[a-z0-9]+", expected_version):
        raise ArchiveDownloadError("Requested OpenSanctions version is invalid")
    if not postgres_dsn:
        raise ArchiveDownloadError("FNS_OPENSANCTIONS_POSTGRES_DSN is not configured")
    try:
        import psycopg
        with psycopg.connect(postgres_dsn, connect_timeout=5):
            pass
    except Exception as error:
        raise ArchiveDownloadError(f"PostgreSQL is unavailable: {type(error).__name__}") from error
    index = importer.fetch_index()
    if index["version"] != expected_version:
        raise ArchiveDownloadError("OpenSanctions snapshot changed; repeat version check")
    range_supported = probe_range(index)
    plan = archive_preflight(index, archive_dir, range_supported=range_supported)
    if not plan["space_sufficient"]:
        raise ArchiveSpaceError(
            f"Недостаточно свободного места: доступно {plan['available_bytes']}, "
            f"требуется {plan['required_free_bytes']} байт"
        )
    write_status_file(status_file, state="downloading", version=expected_version,
                      source_updated_at=index["updated_at"], last_source_change=index["last_change"],
                      expected_entities=index["entity_count"], archive_size_bytes=index["resource_size"],
                      archive_checksum=index["resource_checksum"], target_directory=str(archive_dir),
                      available_bytes=plan["available_bytes"], required_free_bytes=plan["required_free_bytes"],
                      range_supported=range_supported,
                      download_mode="parallel" if range_supported else "single-stream", error=None)
    archive_result = download_archive(index, archive_dir, status_file)
    archive_path = Path(archive_result["archive_path"])
    write_status_file(status_file, state="postgres_importing", version=expected_version,
                      archive_path=str(archive_path), archive_size_bytes=index["resource_size"],
                      archive_checksum=index["resource_checksum"], expected_entities=index["entity_count"],
                      source_updated_at=index["updated_at"], last_source_change=index["last_change"],
                      postgres_state="importing", error=None)
    from scripts.import_opensanctions_postgres import import_archive as import_postgres_archive
    postgres_result = import_postgres_archive(
        archive_path,
        expected_version,
        dsn=postgres_dsn,
        status_file=status_file,
        expected_size=index["resource_size"],
        expected_checksum=index["resource_checksum"],
        expected_entities=index["entity_count"],
    )
    result = {
        "state": "complete",
        "version": expected_version,
        **archive_result,
        "expected_entities": index["entity_count"],
        "source_updated_at": index["updated_at"],
        "last_source_change": index["last_change"],
        "postgres_state": postgres_result["state"],
        "postgres_synced_companies": postgres_result["synced_companies"],
        "completed_at": datetime.now(UTC).isoformat(),
        "error": None,
    }
    write_status_file(status_file, **result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-version", required=True)
    arguments = parser.parse_args()
    try:
        result = run_archive_job(arguments.expected_version)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        state = "interrupted" if isinstance(error, (RetryableSegmentError, ArchiveDownloadError)) else "failed"
        write_status_file(STATUS_FILE, state=state, version=arguments.expected_version,
                          error=f"{type(error).__name__}: {error}")
        print(f"OpenSanctions archive job failed: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)