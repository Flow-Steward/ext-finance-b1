"""Review 2026-11-17, item 1: a search page that does not show its records is no proof
that nothing is there, so no everyday step creates anything after it."""

from __future__ import annotations

from typing import Any

import pytest
from support import FakeB1, ok, page, run

CLIENT = {"code": "123", "name": "UAB", "location_id": 1}
BAD_PAGES = [
    pytest.param({"code": 200, "data": {}, "records": 1}, id="data-object"),
    pytest.param({"code": 200, "data": None}, id="data-null"),
    pytest.param({"code": 200, "page": 1, "records": 0}, id="data-missing"),
    pytest.param({"code": 200, "data": "none"}, id="data-text"),
    pytest.param(page([], records=1), id="empty-but-records-1"),
    pytest.param(page([], hasMore=True), id="empty-but-has-more"),
    pytest.param(page([{"code": "123"}]), id="row-without-id"),
]


@pytest.mark.parametrize("answer", BAD_PAGES)
def test_1_no_client_is_created_after_a_page_that_proves_nothing(answer: Any) -> None:
    fake = FakeB1({"clients/list": answer, "clients/create": ok({"id": 7})})
    response = run(fake, "find_or_create_client", CLIENT)
    assert response["error_code"] == "invalid_response", response
    assert response["definitely_no_external_effect"] is True
    assert "clients/create" not in fake.paths()


@pytest.mark.parametrize("answer", BAD_PAGES[:3])
def test_1_no_sale_is_created_after_a_page_that_proves_nothing(answer: Any) -> None:
    invoice = {
        "transaction_id": "SHOP-1001",
        "sale_date": "2026-11-16",
        "warehouse_id": 1,
        "client_id": 2,
        "operation_type_id": 3,
        "employee_id": 4,
        "lines": [{"item_id": 10, "quantity": "2", "price_without_vat": "10.50"}],
    }
    fake = FakeB1({"warehouse/sales/list": answer, "warehouse/sales/create": ok({"id": 1})})
    response = run(fake, "create_sales_invoice", invoice)
    assert response["error_code"] == "invalid_response", response
    assert fake.paths() == ["warehouse/sales/list"]


@pytest.mark.parametrize("answer", BAD_PAGES[:3])
def test_1_no_payment_is_recorded_after_a_page_that_proves_nothing(answer: Any) -> None:
    inputs = {
        "sale_id": 100,
        "payment_id": "PAY-1",
        "payment_date": "2026-11-16",
        "amount": "25.41",
        "tax": "0.63",
        "currency": "EUR",
        "purpose": "Invoice S-1",
    }
    fake = FakeB1({"bank/transactions/list": answer, "bank/sale-invoice/payment": ok({})})
    response = run(fake, "record_sale_payment", inputs)
    assert response["error_code"] == "invalid_response", response
    assert fake.paths() == ["bank/transactions/list"]


def test_1_find_client_on_an_empty_page_with_records_stops() -> None:
    response = run(FakeB1({"clients/list": page([], records=3)}), "find_client", {"code": "1"})
    assert response["error_code"] == "invalid_response", response


def test_1_an_empty_page_that_agrees_with_itself_is_still_nothing_found() -> None:
    fake = FakeB1({"clients/list": page([]), "clients/create": ok({"id": 7})})
    response = run(fake, "find_or_create_client", CLIENT)
    assert response["ok"] is True, response
    assert response["result"]["client_id"] == 7
