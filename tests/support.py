"""A fake B1 (Site.pro Accounting) API, an in-memory artifact plane and helpers."""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from decimal import Decimal
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit

from runtime.operations import handle_runtime
from runtime.transport import B1Transport, parse_json

BUNDLE = Path(__file__).resolve().parents[1]
API_KEY = "b1-fixture-ApiKey-0123456789abcdef"  # pragma: allowlist secret
PREFIX = "/My-Accounting/api/"


class Call:
    def __init__(self, request: Any) -> None:
        parts = urlsplit(request.full_url)
        self.url = request.full_url
        self.path = parts.path[len(PREFIX) :] if parts.path.startswith(PREFIX) else parts.path
        self.verb = request.get_method()
        self.headers = {k.lower(): v for k, v in request.header_items()}
        self.raw_body = request.data or b""
        self.body: Any = None
        if self.headers.get("content-type", "").startswith("application/json"):
            self.body = parse_json(self.raw_body)


class Response:
    def __init__(self, status: int, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.status = status
        self._body = body
        self.headers = Message()
        for key, value in (headers or {"Content-Type": "application/json"}).items():
            self.headers[key] = value

    def read(self, size: int = -1) -> bytes:
        chunk, self._body = (
            (self._body, b"") if size < 0 else (self._body[:size], self._body[size:])
        )
        return chunk

    def __enter__(self) -> Response:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def ok(data: Any = None, **extra: Any) -> dict[str, Any]:
    return {"code": 200, "message": "OK", "data": data, **extra}


def page(rows: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {"code": 200, "page": 1, "pages": 1, "records": len(rows), "data": rows, **extra}


def refusal(code: int, message: str = "Data validation failure.", **problems: Any) -> tuple:
    return (
        code,
        {"code": code, "shortMessage": "Error", "message": message, "errors": problems or {}},
    )


def file(content: bytes, name: str = "invoice.pdf", kind: str = "application/pdf") -> tuple:
    return (
        200,
        content,
        {"Content-Type": kind, "Content-Disposition": f'attachment; filename="{name}"'},
    )


def _encode(value: Any) -> bytes:
    def default(item: Any) -> Any:
        if isinstance(item, Decimal):
            return float(item)
        raise TypeError

    return json.dumps(value, default=default).encode()


class FakeB1:
    """Answers by path; a list of answers is used in order.

    An answer is a dict (JSON, HTTP 200), a (status, body[, headers]) tuple, an exception
    to raise or a callable taking the Call.
    """

    def __init__(self, routes: dict[str, Any] | None = None, **named: Any) -> None:
        merged = {
            **(routes or {}),
            **{k.replace("__", "/").replace("_", "-"): v for k, v in named.items()},
        }
        self.routes = {k: (list(v) if isinstance(v, list) else v) for k, v in merged.items()}
        self.calls: list[Call] = []

    def __call__(self, request: Any, *, timeout_seconds: float, purpose: str) -> Response:
        call = Call(request)
        self.calls.append(call)
        route = self.routes.get(call.path)
        if route is None:
            raise AssertionError(f"unexpected call to {call.path}")
        answer = route.pop(0) if isinstance(route, list) else route
        if callable(answer) and not isinstance(answer, BaseException):
            answer = answer(call)
        if isinstance(answer, BaseException):
            raise answer
        headers = None
        if isinstance(answer, tuple):
            status, body = answer[0], answer[1]
            headers = answer[2] if len(answer) > 2 else None
        else:
            status, body = 200, answer
        raw = body if isinstance(body, bytes) else _encode(body)
        if status >= 300:
            raise HTTPError(request.full_url, status, "error", Message(), io.BytesIO(raw))
        return Response(status, raw, headers)

    def paths(self) -> list[str]:
        return [c.path for c in self.calls]


class Files:
    """An in-memory artifact plane."""

    def __init__(self, content: bytes = b"%PDF-1.4 test", fail: bool = False) -> None:
        self.content = content
        self.fail = fail
        self.written: list[dict[str, Any]] = []

    def reader(self, payload: Any, *, artifact_id: str, timeout_seconds: float) -> bytes:
        return self.content

    def writer(self, payload: Any, chunks: list[bytes], **kw: Any) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("storage down")
        self.written.append({"data": b"".join(chunks), **kw})
        return {"artifact_handle": f"art_{len(self.written)}"}


def payload(
    operation_id: str,
    inputs: dict[str, Any] | None = None,
    *,
    test_mode: bool = False,
    api_key: str = API_KEY,
) -> dict[str, Any]:
    return {
        "contract_version": "extension_host_v2",
        "mode": "action",
        "runtime_context": {
            "group_id": None,
            "for_each_id": None,
            "step_id": "s",
            "step_execution_id": "5c1d2e3f-4a5b-4c6d-8e7f-000000000001",
            "test_mode": test_mode,
        },
        "action": {
            "action_id": operation_id,
            "input": {"connection_ref": "c1", **(inputs or {})},
            "target": {
                "connection": {
                    "connection_id": "c1",
                    "connection_type_id": "b1",
                    "config": {"label": "UAB X"},
                    "secrets": {"api_key": api_key},
                }
            },
        },
    }


def run(
    fake: FakeB1,
    operation_id: str,
    inputs: dict[str, Any] | None = None,
    *,
    clock: Callable[[], float] | None = None,
    files: Files | None = None,
    **kw: Any,
) -> dict[str, Any]:
    files = files or Files()

    def factory(connection: Any) -> B1Transport:
        if clock is None:
            return B1Transport(connection, opener=fake)
        return B1Transport(connection, opener=fake, clock=clock)

    return handle_runtime(
        payload(operation_id, inputs, **kw),
        transport_factory=factory,
        artifact_reader=files.reader,
        artifact_writer=files.writer,
    )


def dumped(response: Any) -> str:
    return json.dumps(response, default=str, ensure_ascii=False)
