"""Where the key travels, and how every answer, refusal and failure is reported."""

from __future__ import annotations

import io
import socket
from email.message import Message
from typing import Any
from urllib.error import HTTPError

import pytest
from flowsteward_extension_sdk import PinnedPeerError
from support import API_KEY, FakeB1, dumped, ok, payload, refusal, run

from runtime.connection import connection_from_payload
from runtime.operations import handle_runtime
from runtime.transport import B1Transport, dumps_json

CLIENT = {"name": "UAB Pirkejas", "locationId": 1}


def write(answer: Any, operation: str = "clients_create", inputs: dict | None = None) -> dict:
    path = "clients/create" if operation == "clients_create" else "shop/orders/add"
    return run(FakeB1({path: answer}), operation, inputs or CLIENT)


SHOP = {
    "prefix": "p",
    "orderId": 1,
    "orderDate": "2026-11-16",
    "orderNo": "1",
    "currency": "EUR",
    "discount": "0",
    "total": "1",
    "billing": {"name": "UAB", "isCompany": 1, "country": "LT"},
    "delivery": {"isCompany": 1, "country": "LT"},
    "items": [{"name": "A", "quantity": "1", "price": "1", "sum": "1"}],
}


def test_the_key_travels_only_in_its_header_over_https() -> None:
    fake = FakeB1({"clients/create": ok({"id": 5})})
    response = run(fake, "clients_create", CLIENT)
    assert response["ok"] is True, response
    [call] = fake.calls
    assert call.url == "https://site.pro/My-Accounting/api/clients/create"
    assert call.verb == "POST"
    assert call.headers["b1-api-key"] == API_KEY
    assert API_KEY not in call.url and API_KEY.encode() not in call.raw_body
    assert call.body == {"name": "UAB Pirkejas", "locationId": 1}
    assert response["result"]["id"] == 5
    assert response["external_effect_status"] == "succeeded"


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (
            refusal(401, errors_=None) if False else refusal(401, apiKey=["API key is required."]),
            "authentication_failed",
        ),
        (refusal(403, "Forbidden"), "authentication_failed"),
        (refusal(409, "Object already exists"), "conflict"),
        (refusal(400, name=["Name is required."]), "upstream_validation_failed"),
    ],
)
def test_refusals_of_a_single_write_change_nothing(answer: Any, code: str) -> None:
    response = write(answer)
    assert response["error_code"] == code, response
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"


def test_a_403_says_the_key_may_be_frozen_or_read_only() -> None:
    response = write(refusal(403, "Forbidden"))
    assert "frozen" in response["error"] and "read-only" in response["error"]


def test_a_400_of_a_write_of_several_records_is_unknown() -> None:
    response = write(refusal(400), "shop_orders_add", SHOP)
    assert response["error_code"] == "upstream_validation_failed"
    assert response["external_effect_status"] == "timeout_unknown"


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        (refusal(480, "Partial completion"), "upstream_failure"),
        (refusal(404, "Not found"), "not_found"),
        ((500, b"oops"), "upstream_failure"),
        ((503, b""), "upstream_failure"),
        ((429, b""), "upstream_failure"),
        ((504, b""), "timeout"),
        ((302, b""), "redirect_rejected"),
        (b"<html>not json</html>", "invalid_response"),
        ({"code": 400, "message": "inside 200"}, "upstream_validation_failed"),
        (TimeoutError(), "timeout_unknown"),
        (socket.timeout(), "timeout_unknown"),
        (ConnectionResetError(), "timeout_unknown"),
    ],
)
def test_every_other_failure_after_a_write_was_sent_is_unknown(answer: Any, code: str) -> None:
    response = write(answer)
    assert response["error_code"] == code, response
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False


@pytest.mark.parametrize(
    ("answer", "code", "retryable"),
    [
        (refusal(401), "authentication_failed", False),
        (refusal(403), "authentication_failed", False),
        (refusal(400), "upstream_validation_failed", False),
        ((503, b""), "upstream_failure", True),
        ((429, b""), "upstream_failure", True),
        (TimeoutError(), "timeout", True),
        (b"not json", "invalid_response", False),
    ],
)
def test_read_failures_change_nothing(answer: Any, code: str, retryable: bool) -> None:
    response = run(
        FakeB1({"reference-book/currencies/list": answer}),
        "reference_book_currencies_list",
        {"rows": 10},
    )
    assert response["error_code"] == code, response
    assert response["definitely_no_external_effect"] is True
    assert response.get("retryable", False) is retryable


def test_the_key_is_never_in_an_answer_or_an_error() -> None:
    for answer in (
        refusal(400, f"bad {API_KEY}"),
        (500, f"<html>{API_KEY}</html>".encode()),
        ok({"note": API_KEY, "id": 1}),
    ):
        response = write(answer)
        assert API_KEY not in dumped(response)


def test_http_errors_never_pass_on_the_address_or_the_key() -> None:
    def boom(call: Any) -> Any:
        raise HTTPError(call.url, 500, f"error {call.headers}", Message(), io.BytesIO(b""))

    response = run(
        FakeB1({"reference-book/currencies/list": boom}),
        "reference_book_currencies_list",
        {"rows": 10},
    )
    assert API_KEY not in dumped(response)


def test_an_internal_error_reports_only_its_place() -> None:
    def boom(call: Any) -> Any:
        raise RuntimeError(f"secret {API_KEY}")

    response = run(
        FakeB1({"reference-book/currencies/list": boom}),
        "reference_book_currencies_list",
        {"rows": 10},
    )
    assert response["error_code"] == "internal_error"
    assert API_KEY not in dumped(response)


def test_resolution_and_blocked_addresses_are_before_sending() -> None:
    assert (
        write(PinnedPeerError("site.pro cannot be resolved"))["definitely_no_external_effect"]
        is True
    )
    assert write(PinnedPeerError("blocked"))["error_code"] == "blocked_address"


def test_no_request_starts_without_time_left() -> None:
    times = iter([0.0])
    fake = FakeB1({"clients/create": ok({"id": 1})})
    response = run(fake, "clients_create", CLIENT, clock=lambda: next(times, 1000.0))
    assert response["error_code"] == "timeout"
    assert response["definitely_no_external_effect"] is True
    assert fake.calls == []


def test_an_answer_trickling_past_the_deadline_is_unknown() -> None:
    now = [0.0]

    class Slow:
        status = 200
        headers = Message()

        def read(self, size: int = -1) -> bytes:
            now[0] += 400.0
            return b"{"

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *exc: Any) -> None:
            return None

    connection = connection_from_payload(payload("clients_create"), connection_ref="c1")
    transport = B1Transport(connection, opener=lambda r, **kw: Slow(), clock=lambda: now[0])
    response = handle_runtime(
        payload("clients_create", CLIENT), transport_factory=lambda c: transport
    )
    assert response["error_code"] == "timeout_unknown"


@pytest.mark.parametrize("key", ["", "short", "has space inside", "x" * 257, "ąčęėįšųū12345"])
def test_unusable_keys_are_refused_before_any_request(key: str) -> None:
    fake = FakeB1()
    response = run(fake, "reference_book_currencies_list", {"rows": 10}, api_key=key)
    assert response["error_code"] == "invalid_connection"
    assert fake.calls == []


def test_decimals_travel_exactly() -> None:
    from decimal import Decimal

    assert dumps_json({"a": Decimal("1.10"), "b": Decimal("100"), "c": [Decimal("0.0001")]}) == (
        '{"a":1.10,"b":100,"c":[0.0001]}'
    )


def test_unknown_operations_are_refused() -> None:
    response = run(FakeB1(), "warehouse_sales_purge", {"ids": [1]})
    assert response["error_code"] == "unsupported_operation"
    assert response["definitely_no_external_effect"] is True
