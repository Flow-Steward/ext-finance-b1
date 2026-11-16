"""The only way this extension reaches B1 (Site.pro Accounting).

Every documented operation is a POST to ``https://site.pro/My-Accounting/api/<path>``
(``connection.BASE_URL``) with a JSON body — or, for file uploads, the file's bytes
with ``B1-File-Name`` and its type. The key travels only in the ``B1-Api-Key``
header. Requests go out through the public Flow Steward extension SDK, which pins
DNS, verifies the connected peer, refuses redirects and enforces the timeout; they
are sent one at a time, never in parallel.

Answers are a JSON object ``{"code", "message", "data"}`` (``code`` 200 on success)
or, for the file operations, the file's bytes. Refusals carry the HTTP status and a
JSON object ``{"code", "shortMessage", "message", "errors"}`` (checked with no key
and with an invalid one). The meaning of the statuses (documentation 0.3.23 and the
vendor's PHP library): 400 validation, 401 missing or invalid key, 403 a frozen key
or one without the right, 404 not found, 409 "Object already exists", 480 "Partial
completion", 500, 503.

Outcome of a write: 401, 403 and 409 changed nothing; 400 changed nothing only for a
write of one object (``single_object``); 480 and every other failure after a write
was sent leave it unknown (``timeout_unknown``). Writes are never retried.
"""

from __future__ import annotations

import http.client
import json
import re
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request

from flowsteward_extension_sdk import PinnedPeerError, open_pinned_url

from . import errors
from .connection import BASE_URL, Connection
from .errors import ExtensionError

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024
#: The most read from a JSON answer (a list page of 500 rows fits well inside).
MAX_ANSWER_BYTES = 30 * 1024 * 1024
#: The most read from a file answer.
MAX_FILE_BYTES = 40 * 1024 * 1024
MAX_ERROR_BODY_BYTES = 64 * 1024
CHUNK_BYTES = 64 * 1024
#: Shortest window still worth starting a request in.
MIN_CALL_WINDOW_SECONDS = 15.0
_USER_AGENT = "FlowSteward-B1/0.1"
_PATH_RE = re.compile(r"^[a-z0-9-]+(/[a-z0-9-]+){1,3}$")
_FILENAME_RE = re.compile(r"filename\*?=(?:UTF-8'')?\"?([^\";]+)\"?", re.IGNORECASE)


class DeadlineReached(Exception):
    """The invocation's time budget leaves no room for another request."""


@dataclass
class Answer:
    status: int
    #: The JSON answer object, or {} for a file answer.
    data: dict[str, Any] = field(default_factory=dict)
    #: The file's bytes, for a file answer.
    file: bytes | None = None
    content_type: str = ""
    file_name: str = ""


class B1Transport:
    """Sends B1 requests for one connection."""

    def __init__(
        self,
        connection: Connection,
        *,
        opener: Callable[..., Any] = open_pinned_url,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._connection = connection
        self._opener = opener
        self.clock = clock
        self._timeout_seconds = timeout_seconds
        self._call_timeout = timeout_seconds
        #: True once a request that can change data may have left this process.
        self.mutated = False
        #: True once B1 confirmed a change in this invocation.
        self.committed = False
        #: Monotonic time after which no request may start (set by the operation).
        self.deadline: float | None = None

    @property
    def connection(self) -> Connection:
        return self._connection

    def remaining(self) -> float:
        return float("inf") if self.deadline is None else self.deadline - self.clock()

    # -- public calls --------------------------------------------------------

    def read(self, path: str, body: Mapping[str, Any]) -> dict[str, Any]:
        """A read: its JSON answer object."""
        return self._json_call(path, body, mutating=False, single_object=True).data

    def read_file(self, path: str, body: Mapping[str, Any]) -> Answer:
        """A read that answers with a file."""
        return self._call(
            path,
            dumps_json(body).encode("utf-8"),
            "application/json; charset=utf-8",
            {},
            mutating=False,
            single_object=True,
            expect_file=True,
        )

    def write(self, path: str, body: Mapping[str, Any], *, single_object: bool) -> dict[str, Any]:
        """A write: its JSON answer object, once B1 confirmed it."""
        answer = self._json_call(path, body, mutating=True, single_object=single_object)
        self.committed = True
        return answer.data

    def upload(
        self, path: str, content: bytes, *, content_type: str, headers: Mapping[str, str]
    ) -> dict[str, Any]:
        """A file upload: the bytes as the body, the record and name in headers."""
        answer = self._call(
            path,
            content,
            content_type,
            headers,
            mutating=True,
            single_object=True,
            expect_file=False,
        )
        self.committed = True
        return answer.data

    # -- one request ---------------------------------------------------------

    def _json_call(
        self, path: str, body: Mapping[str, Any], *, mutating: bool, single_object: bool
    ) -> Answer:
        encoded = dumps_json(body).encode("utf-8")
        return self._call(
            path,
            encoded,
            "application/json; charset=utf-8",
            {},
            mutating=mutating,
            single_object=single_object,
            expect_file=False,
        )

    def _call(
        self,
        path: str,
        body: bytes,
        content_type: str,
        headers: Mapping[str, str],
        *,
        mutating: bool,
        single_object: bool,
        expect_file: bool,
    ) -> Answer:
        if not _PATH_RE.fullmatch(path):
            raise errors.invalid("Not a Site.pro Accounting operation")
        if len(body) > MAX_REQUEST_BODY_BYTES:
            raise errors.invalid("The request is larger than the 12 MB this extension sends")
        request_headers = {
            "Accept": "application/json, */*",
            "Content-Type": content_type,
            "User-Agent": _USER_AGENT,
            **{name: value for name, value in headers.items()},
            "B1-Api-Key": self._connection.api_key,
        }
        request = Request(f"{BASE_URL}/{path}", method="POST", data=body, headers=request_headers)
        status, raw, response_headers = self._send(
            request,
            path,
            mutating=mutating,
            single_object=single_object,
            limit=MAX_FILE_BYTES if expect_file else MAX_ANSWER_BYTES,
        )
        kind = str(response_headers.get("Content-Type") or "")
        if expect_file and not kind.lower().startswith("application/json"):
            disposition = str(response_headers.get("Content-Disposition") or "")
            match = _FILENAME_RE.search(disposition)
            return Answer(
                status,
                file=raw,
                content_type=kind.split(";")[0].strip() or "application/octet-stream",
                file_name=errors.safe_text(match.group(1) if match else "", 200),
            )
        data = self._answer(raw, path, status, mutating=mutating)
        return Answer(status, data=data)

    def _read_expiry(self) -> float | None:
        return None if self.deadline is None else self.deadline + MIN_CALL_WINDOW_SECONDS

    def _send(
        self, request: Request, path: str, *, mutating: bool, single_object: bool, limit: int
    ) -> tuple[int, bytes, Mapping[str, Any]]:
        remaining = self.remaining()
        if remaining < MIN_CALL_WINDOW_SECONDS:
            raise DeadlineReached
        self._call_timeout = min(self._timeout_seconds, remaining)
        if mutating:
            self.mutated = True
        expires = self._read_expiry()
        if expires is None:
            return self._exchange(
                request, path, mutating=mutating, single_object=single_object, limit=limit
            )
        outcome: dict[str, Any] = {}

        def work() -> None:
            try:
                outcome["value"] = self._exchange(
                    request, path, mutating=mutating, single_object=single_object, limit=limit
                )
            except BaseException as exc:  # handed to the caller below
                outcome["error"] = exc

        worker = threading.Thread(target=work, name="b1-call", daemon=True)
        worker.start()
        worker.join(max(0.0, expires - self.clock()))
        if worker.is_alive():
            _late(mutating)
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def _exchange(
        self, request: Request, path: str, *, mutating: bool, single_object: bool, limit: int
    ) -> tuple[int, bytes, Mapping[str, Any]]:
        try:
            with self._opener(
                request, timeout_seconds=self._call_timeout, purpose="Site.pro Accounting"
            ) as response:
                status = int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)
                headers = getattr(response, "headers", None) or {}
                raw = read_bounded(
                    response,
                    limit,
                    mutating=mutating,
                    expires=self._read_expiry(),
                    clock=self.clock,
                    per_read=self._call_timeout,
                )
        except HTTPError as exc:
            try:
                body = exc.read(MAX_ERROR_BODY_BYTES)
            except Exception:  # pragma: no cover - upstream body is optional
                body = b""
            raise self.refusal(
                int(exc.code), body, path, mutating=mutating, single_object=single_object
            ) from None
        except PinnedPeerError as exc:
            # Raised while resolving and pinning, before anything was sent.
            if "cannot be resolved" in str(exc):
                raise ExtensionError(
                    errors.CONNECTION_FAILED,
                    "site.pro could not be resolved; check the network",
                    failure_class="transient",
                    retryable=True,
                    definitely_no_external_effect=True,
                    external_effect_status="failed",
                ) from None
            raise errors.no_effect(
                errors.BLOCKED_ADDRESS, "site.pro is not reachable under the host network policy"
            ) from None
        except TimeoutError:
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.TIMEOUT,
                "Site.pro Accounting did not answer in time" + (CHECK if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        except (OSError, http.client.HTTPException):
            raise ExtensionError(
                errors.TIMEOUT_UNKNOWN if mutating else errors.CONNECTION_FAILED,
                "The connection to Site.pro Accounting failed" + (CHECK if mutating else ""),
                **_transport_failure_facts(mutating=mutating),
            ) from None
        if status >= 300 or status < 200:
            raise self.refusal(
                status,
                raw[:MAX_ERROR_BODY_BYTES],
                path,
                mutating=mutating,
                single_object=single_object,
            )
        return status, raw, headers

    # -- answers -------------------------------------------------------------

    def scrub(self, value: Any) -> Any:
        """The key removed from every text and key of a parsed answer."""
        if isinstance(value, str):
            for form in self._connection.secret_forms():
                if form in value:
                    value = value.replace(form, "[redacted]")
            return value
        if isinstance(value, Mapping):
            return {self.scrub(k): self.scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.scrub(v) for v in value]
        return value

    def _answer(self, raw: bytes, path: str, status: int, *, mutating: bool) -> dict[str, Any]:
        try:
            data = self.scrub(parse_json(raw))
        except ValueError:
            if mutating:
                raise unknown(
                    f"Site.pro Accounting answered {path} (HTTP {status}) with something that "
                    "could not be read" + CHECK,
                    errors.INVALID_RESPONSE,
                    status,
                ) from None
            raise errors.no_effect(
                errors.INVALID_RESPONSE,
                f"Site.pro Accounting answered {path} with something that is not JSON",
                failure_class="provider",
                retryable=False,
                http_status=status,
            ) from None
        code = data.get("code")
        if isinstance(code, int) and not isinstance(code, bool) and code != 200:
            # A refusal inside an HTTP 200 answer.
            raise self.refusal(code, raw, path, mutating=mutating, single_object=False)
        return data

    def detail(self, raw: bytes) -> str:
        """B1's own message and field errors; never the key."""
        try:
            data = self.scrub(parse_json(raw))
        except ValueError:
            text = re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace"))
            return errors.safe_text(self.scrub(text), 200)
        return error_text(data)

    def refusal(
        self, status: int, raw: bytes, path: str, *, mutating: bool, single_object: bool
    ) -> ExtensionError:
        detail = self.detail(raw)
        suffix = f": {detail}" if detail else ""
        if status == 401:
            return errors.no_effect(
                errors.AUTHENTICATION_FAILED,
                f"Site.pro Accounting did not accept the API key (HTTP 401){suffix}. Check the "
                "key in the connection.",
                failure_class="provider",
                retryable=False,
                http_status=status,
            )
        if status == 403:
            return errors.no_effect(
                errors.AUTHENTICATION_FAILED,
                f"Site.pro Accounting refused {path} (HTTP 403){suffix}: the API key is frozen "
                "or may not do this (a read-only key cannot write; the e-commerce steps need an "
                '"API for e-commerce" key)',
                failure_class="provider",
                retryable=False,
                http_status=status,
            )
        if status == 409:
            return errors.no_effect(
                errors.CONFLICT,
                f"Site.pro Accounting already has this {path.split('/')[-2]} (HTTP 409){suffix}; "
                "nothing was saved",
                failure_class="provider",
                retryable=False,
                http_status=status,
            )
        if status == 400 and (not mutating or single_object):
            return errors.no_effect(
                errors.UPSTREAM_VALIDATION_FAILED,
                f"Site.pro Accounting refused {path} (HTTP 400){suffix}"
                + ("; nothing was saved" if mutating else ""),
                failure_class="provider",
                retryable=False,
                http_status=status,
            )
        if 300 <= status < 400:
            code, message = (
                errors.REDIRECT_REJECTED,
                (
                    f"Site.pro Accounting redirected {path} (HTTP {status}); redirects are not followed"
                ),
            )
        elif status == 404:
            code, message = (
                errors.NOT_FOUND,
                f"Site.pro Accounting found nothing for {path}{suffix}",
            )
        elif status == 480:
            code, message = (
                errors.UPSTREAM_FAILURE,
                (f"Site.pro Accounting completed {path} only in part (HTTP 480){suffix}"),
            )
        elif status == 400:
            code, message = (
                errors.UPSTREAM_VALIDATION_FAILED,
                (f"Site.pro Accounting refused {path} (HTTP 400){suffix}"),
            )
        elif status >= 500 or status in {408, 429}:
            code, message = (
                errors.TIMEOUT if status in {408, 504} else errors.UPSTREAM_FAILURE,
                f"Site.pro Accounting could not complete {path} (HTTP {status}){suffix}",
            )
        else:
            code, message = (
                errors.UPSTREAM_VALIDATION_FAILED,
                (f"Site.pro Accounting rejected {path} (HTTP {status}){suffix}"),
            )
        if mutating:
            return unknown(message + CHECK, code, status)
        return ExtensionError(
            code,
            message,
            failure_class="provider",
            retryable=status >= 500 or status in {408, 429},
            definitely_no_external_effect=True,
            external_effect_status="failed",
            http_status=status,
        )


CHECK = "; check in Site.pro Accounting whether it was saved before running the step again"


def unknown(message: str, code: str, status: int | None) -> ExtensionError:
    return ExtensionError(
        code,
        message,
        failure_class="provider",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
        http_status=status,
    )


def dumps_json(value: Any) -> str:
    """JSON with ``Decimal`` written as an exact number (never through float)."""
    marker = secrets.token_hex(8)

    def default(item: Any) -> str:
        if isinstance(item, Decimal) and item.is_finite():
            return f"@{marker}@{format(item, 'f')}@{marker}@"
        raise TypeError(f"{type(item).__name__} is not JSON")

    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=default)
    return re.sub(rf'"@{marker}@([-+0-9.]+)@{marker}@"', r"\1", text)


def parse_json(raw: bytes) -> dict[str, Any]:
    """A JSON object, numbers with a point read as Decimal."""
    text = raw.decode("utf-8-sig", "strict") if raw else ""
    if not text.strip():
        raise ValueError("empty")
    try:
        data = json.loads(text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise ValueError("bad JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def error_text(data: Mapping[str, Any]) -> str:
    """``message`` and the field ``errors`` of a refusal, as one bounded line."""
    parts: list[str] = []
    message = data.get("message")
    if isinstance(message, str) and message.strip():
        parts.append(message.strip())
    problems = data.get("errors")
    if isinstance(problems, Mapping):
        for name, value in list(problems.items())[:10]:
            texts = value if isinstance(value, list) else [value]
            joined = "; ".join(str(t) for t in texts[:3] if t is not None)
            parts.append(f"{name}: {joined}")
    return errors.safe_text(" — ".join(parts), 500)


def read_bounded(
    response: Any,
    limit: int,
    *,
    mutating: bool = False,
    expires: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    per_read: float | None = None,
) -> bytes:
    """Read at most ``limit`` bytes before ``expires``; a longer answer is an error."""
    buffer = bytearray()
    sock = _socket_of(response)
    while True:
        if expires is not None:
            left = expires - clock()
            if left <= 0:
                _late(mutating)
            if sock is not None:
                try:
                    sock.settimeout(max(0.5, min(left, per_read or left)))
                except OSError:  # pragma: no cover - a closed socket fails the read below
                    pass
        chunk = response.read(min(CHUNK_BYTES, limit + 1 - len(buffer)))
        if not chunk:
            break
        buffer.extend(chunk)
        if expires is not None and clock() > expires:
            _late(mutating)
        if len(buffer) > limit:
            if mutating:
                raise unknown(
                    "Site.pro Accounting's answer was too large to read" + CHECK,
                    errors.RESPONSE_TOO_LARGE,
                    None,
                )
            raise errors.no_effect(
                errors.RESPONSE_TOO_LARGE,
                f"Site.pro Accounting's answer is larger than the {limit // (1024 * 1024)} MB "
                "this extension reads; ask for fewer rows",
            )
    return bytes(buffer)


def _late(mutating: bool) -> None:
    if not mutating:
        raise DeadlineReached
    raise ExtensionError(
        errors.TIMEOUT_UNKNOWN,
        "Site.pro Accounting's answer did not arrive in time" + CHECK,
        failure_class="transient",
        retryable=False,
        definitely_no_external_effect=False,
        external_effect_status="timeout_unknown",
    )


def _socket_of(response: Any) -> Any:
    for path in (("fp", "raw", "_sock"), ("fp", "fp", "raw", "_sock"), ("_sock",)):
        node = response
        for name in path:
            node = getattr(node, name, None)
        if node is not None and hasattr(node, "settimeout"):
            return node
    return None


def _transport_failure_facts(*, mutating: bool) -> dict[str, Any]:
    return {
        "failure_class": "transient",
        "retryable": not mutating,
        "definitely_no_external_effect": not mutating,
        "external_effect_status": "timeout_unknown" if mutating else "failed",
    }


__all__ = [
    "CHECK",
    "MIN_CALL_WINDOW_SECONDS",
    "Answer",
    "B1Transport",
    "DeadlineReached",
    "dumps_json",
    "error_text",
    "parse_json",
    "read_bounded",
    "unknown",
]
