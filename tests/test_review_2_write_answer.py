"""Review 2026-11-17, item 2: a write is a success only on an answer that confirms it.

When the answer has ``code``, it must be the integer 200. Without ``code`` the answer is
accepted, but an answer with neither ``code`` nor ``data`` is said in the warnings, and an
everyday step that needs the new record's id cannot go on without it.
"""

from __future__ import annotations

from typing import Any

import pytest
from support import FakeB1, ok, page, run

BAD_CODES = [
    pytest.param({"code": None, "data": {"id": 1}}, id="code-null"),
    pytest.param({"code": True, "data": {"id": 1}}, id="code-true"),
    pytest.param({"code": "480", "message": "Error"}, id="code-text-error"),
    pytest.param({"code": "200", "data": {"id": 1}}, id="code-text-200"),
    pytest.param({"code": 200.0, "data": {"id": 1}}, id="code-float"),
    pytest.param({"code": [200], "data": {"id": 1}}, id="code-list"),
]


@pytest.mark.parametrize("answer", BAD_CODES)
def test_2_a_write_answer_with_a_code_other_than_200_is_unknown(answer: Any) -> None:
    fake = FakeB1({"clients/create": answer})
    response = run(fake, "clients_create", {"name": "A", "locationId": 1})
    assert response["ok"] is False, response
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False
    assert response["error_code"] == "invalid_response"


@pytest.mark.parametrize("answer", BAD_CODES)
def test_2_a_delete_answer_with_a_code_other_than_200_is_unknown(answer: Any) -> None:
    fake = FakeB1({"warehouse/sales/delete": answer})
    response = run(fake, "warehouse_sales_delete", {"ids": [5]})
    assert response["external_effect_status"] == "timeout_unknown", response


@pytest.mark.parametrize("answer", BAD_CODES)
def test_2_a_read_answer_with_a_code_other_than_200_is_invalid(answer: Any) -> None:
    response = run(FakeB1({"clients/list": answer}), "clients_list", {})
    assert response["error_code"] == "invalid_response", response
    assert response["definitely_no_external_effect"] is True


def test_2_a_write_answer_with_an_error_code_inside_http_200_is_a_refusal() -> None:
    fake = FakeB1({"clients/create": {"code": 400, "message": "Data validation failure."}})
    response = run(fake, "clients_create", {"name": "A", "locationId": 1})
    assert response["ok"] is False
    assert response["error_code"] == "upstream_validation_failed"


@pytest.mark.parametrize("answer", [{}, {"message": "OK"}])
def test_2_a_bare_write_answer_is_a_success_that_says_so(answer: Any) -> None:
    response = run(
        FakeB1({"clients/create": answer}), "clients_create", {"name": "A", "locationId": 1}
    )
    assert response["ok"] is True, response
    assert response["external_effect_status"] == "succeeded"
    assert response["result"]["id"] is None
    assert any("without an answer" in w for w in response["result"]["warnings"])


def test_2_a_write_answer_with_data_and_no_code_is_a_plain_success() -> None:
    answer = {"data": {"id": 9}}  # the one documented success example has no code
    response = run(
        FakeB1({"clients/create": answer}), "clients_create", {"name": "A", "locationId": 1}
    )
    assert response["ok"] is True and response["result"]["id"] == 9
    assert response["result"]["warnings"] == []


@pytest.mark.parametrize("answer", [{}, ok(None), ok({"name": "UAB"})])
def test_2_a_created_client_without_an_id_is_unknown(answer: Any) -> None:
    fake = FakeB1({"clients/list": page([]), "clients/create": answer})
    response = run(fake, "find_or_create_client", {"code": "123", "name": "UAB", "location_id": 1})
    assert response["ok"] is False, response
    assert response["external_effect_status"] == "timeout_unknown"
    assert "id" in response["error"]


def test_2_a_created_item_without_an_id_is_unknown() -> None:
    fake = FakeB1({"reference-book/items/list": page([]), "reference-book/items/create": {}})
    response = run(
        fake,
        "find_or_create_item",
        {
            "code": "A1",
            "name": "Widget",
            "attribute_id": 1,
            "measurement_unit_id": 2,
            "price_without_vat": "10.5",
            "vat_rate": "21",
        },
    )
    assert response["external_effect_status"] == "timeout_unknown", response
