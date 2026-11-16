"""Project-scoped B1 (Site.pro Accounting) connection: one company through its API key.

The key comes from Settings → Integrations in Site.pro Accounting ("API simplified",
or "API for e-commerce" for the e-commerce steps). It is the only setting: the
address is fixed (``BASE_URL``), so a workflow can never send the key anywhere else,
and never over plain http.

The key lives in a private field of a frozen dataclass whose ``repr`` never shows
it; it travels only in the ``B1-Api-Key`` header and is never placed in a result, a
log line or an exception message.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, quote_plus

from . import errors
from .errors import ExtensionError

CONNECTION_TYPE_ID = "b1"
#: The documented API address (api_project.json "url"), always over https.
BASE_URL = "https://site.pro/My-Accounting/api"
HOST = "site.pro"
CONFIG_FIELDS: frozenset[str] = frozenset({"label"})
SECRET_FIELDS: frozenset[str] = frozenset({"api_key"})

#: Shorter keys could not be removed from answers without mangling them.
MIN_KEY_LENGTH = 8
MAX_KEY_LENGTH = 256
#: Printable ASCII without spaces: a header value that cannot be split.
_KEY_RE = re.compile(r"^[\x21-\x7e]+$")


@dataclass(frozen=True)
class Connection:
    """One validated B1 connection."""

    connection_id: str
    _api_key: str = field(repr=False)

    @property
    def api_key(self) -> str:
        return self._api_key

    def secret_forms(self) -> tuple[str, ...]:
        """Every way the key can appear in a text: as is and encoded."""
        key = self._api_key
        forms = {
            key,
            quote_plus(key, safe=""),
            quote(key, safe=""),
            json.dumps(key, ensure_ascii=False)[1:-1],
            html.escape(key, quote=True),
            html.escape(key, quote=False),
        }
        # Longest first, so a form that contains another is removed whole.
        return tuple(sorted((f for f in forms if f), key=len, reverse=True))

    def __repr__(self) -> str:  # pragma: no cover - defensive
        return f"Connection(connection_id={self.connection_id!r})"

    __str__ = __repr__


def _invalid(message: str) -> ExtensionError:
    return errors.no_effect(errors.INVALID_CONNECTION, message)


def _api_key(value: Any) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if not text:
        raise _invalid("Add the API key from Site.pro Accounting to this connection")
    if len(text) < MIN_KEY_LENGTH or len(text) > MAX_KEY_LENGTH or not _KEY_RE.fullmatch(text):
        raise _invalid("The API key is not usable: 8 to 256 printable characters without spaces")
    return text


def connection_from_payload(payload: Mapping[str, Any], *, connection_ref: str) -> Connection:
    """Validate the selected project connection before any outbound request."""
    action = payload.get("action")
    target = action.get("target") if isinstance(action, Mapping) else None
    connection = target.get("connection") if isinstance(target, Mapping) else None
    if not isinstance(connection, Mapping):
        raise _invalid("The selected connection is unavailable")
    connection_id = str(connection.get("connection_id") or "")
    if not connection_id or (connection_ref and connection_id != connection_ref):
        raise _invalid("The selected connection does not match connection_ref")
    connection_type = str(
        connection.get("connection_type_id") or connection.get("connection_type") or ""
    )
    if connection_type and connection_type != CONNECTION_TYPE_ID:
        raise _invalid("The selected connection is not supported")
    secrets = connection.get("secrets")
    secrets = secrets if isinstance(secrets, Mapping) else {}
    if set(secrets) - SECRET_FIELDS:
        raise _invalid("The connection carries unsupported secrets")
    return Connection(connection_id=connection_id, _api_key=_api_key(secrets.get("api_key")))


__all__ = [
    "BASE_URL",
    "CONFIG_FIELDS",
    "CONNECTION_TYPE_ID",
    "HOST",
    "SECRET_FIELDS",
    "Connection",
    "connection_from_payload",
]
