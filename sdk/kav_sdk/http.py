"""HTTP/OpenAPI v0.1 projection of the four adapter operations (D-026).

Stdlib only. Payload JSON Schemas in contracts/ remain canonical (ADR-003).
"""
from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from kav_sdk.adapter import HostAdapter
from kav_sdk.models import ExperimentResult, ExperimentSpec, ProjectManifest, SearchSpace

_OPENAPI_NAME = "adapter-http.openapi.json"
_CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "contracts"


def load_openapi() -> dict[str, Any]:
    """Load the committed OpenAPI document; fall back to a path-only stub."""
    path = _CONTRACTS_DIR / _OPENAPI_NAME
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "openapi": "3.0.3",
        "info": {"title": "KAV Host Adapter HTTP", "version": "0.1"},
        "paths": {
            "/v0.1/manifest": {"get": {}},
            "/v0.1/search-space": {"get": {}},
            "/v0.1/experiments": {"post": {}},
            "/v0.1/results": {"post": {}},
            "/v0.1/openapi.json": {"get": {}},
        },
    }


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, default=str).encode("utf-8")


def make_handler(adapter: HostAdapter) -> type[BaseHTTPRequestHandler]:
    """Build a BaseHTTPRequestHandler class bound to one HostAdapter."""
    openapi = load_openapi()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: object) -> None:
            return

        def _send(self, status: int, payload: Any) -> None:
            body = _json_bytes(payload)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> Any:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length else b""
            if not raw:
                raise ValueError("empty body")
            return json.loads(raw.decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802 — http.server API
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            if path == "/v0.1/manifest":
                self._send(200, adapter.manifest().model_dump(mode="json"))
                return
            if path == "/v0.1/search-space":
                self._send(200, adapter.search_space().model_dump(mode="json"))
                return
            if path == "/v0.1/openapi.json":
                self._send(200, openapi)
                return
            self._send(404, {"error": {"code": "not_found", "message": path}})

        def do_POST(self) -> None:  # noqa: N802 — http.server API
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            try:
                data = self._read_json()
            except (ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": {"code": "invalid_json", "message": str(exc)[:500]}})
                return
            if path == "/v0.1/experiments":
                try:
                    spec = ExperimentSpec.model_validate(data)
                except ValidationError as exc:
                    self._send(400, {"error": {"code": "invalid_spec", "message": str(exc)[:500]}})
                    return
                result = adapter.run_experiment(spec)
                self._send(200, result.model_dump(mode="json"))
                return
            if path == "/v0.1/results":
                try:
                    result = ExperimentResult.model_validate(data)
                except ValidationError as exc:
                    self._send(400, {"error": {"code": "invalid_result", "message": str(exc)[:500]}})
                    return
                reported = adapter.report_result(result)
                self._send(200, reported.model_dump(mode="json"))
                return
            self._send(404, {"error": {"code": "not_found", "message": path}})

    return Handler


class AdapterServer:
    """Threading HTTP server wrapping a HostAdapter. Use as a context manager in tests."""

    def __init__(self, adapter: HostAdapter, host: str = "127.0.0.1", port: int = 0) -> None:
        self._httpd = ThreadingHTTPServer((host, port), make_handler(adapter))
        self._thread: Thread | None = None

    @property
    def base_url(self) -> str:
        h, p = self._httpd.server_address[:2]
        return f"http://{h}:{p}"

    def start(self) -> "AdapterServer":
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def __enter__(self) -> "AdapterServer":
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        self.stop()


class HttpHostAdapter:
    """HostAdapter client over the v0.1 HTTP projection."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        parsed = urlparse(base_url)
        if parsed.hostname is None:
            raise ValueError("base_url must include a host")
        self._host = parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._timeout = timeout

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        payload = _json_bytes(body) if body is not None else None
        conn = HTTPConnection(self._host, self._port, timeout=self._timeout)
        try:
            headers = {"Accept": "application/json"}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            if resp.status >= 400:
                err = data.get("error") if isinstance(data, dict) else None
                msg = err.get("message") if isinstance(err, dict) else raw[:500]
                raise RuntimeError(f"HTTP {resp.status}: {msg}")
            return data
        finally:
            conn.close()

    def manifest(self) -> ProjectManifest:
        return ProjectManifest.model_validate(self._request("GET", "/v0.1/manifest"))

    def search_space(self) -> SearchSpace:
        return SearchSpace.model_validate(self._request("GET", "/v0.1/search-space"))

    def run_experiment(self, spec: ExperimentSpec) -> ExperimentResult:
        return ExperimentResult.model_validate(
            self._request("POST", "/v0.1/experiments", spec.model_dump(mode="json"))
        )

    def report_result(self, result: ExperimentResult) -> ExperimentResult:
        return ExperimentResult.model_validate(
            self._request("POST", "/v0.1/results", result.model_dump(mode="json"))
        )
