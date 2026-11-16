"""Everyday steps: strict searches, repeats refused, honest half-way failures."""

from __future__ import annotations

from typing import Any

import pytest
from support import FakeB1, Files, file, ok, page, refusal, run

from runtime import composites


def test_test_connection_lists_ten_currencies() -> None:
    fake = FakeB1({"reference-book/currencies/list": page([{"id": 1}])})
    response = run(fake, "test_connection")
    assert response["result"] == {"connected": True, "warnings": []}
    assert fake.calls[0].body == {"rows": 10}
    refused = run(FakeB1({"reference-book/currencies/list": refusal(401)}), "test_connection")
    assert refused["error_code"] == "authentication_failed"


def test_find_client_is_strict_and_rechecks_the_filter() -> None:
    rows = [{"id": 1, "code": "123", "vatCode": "LT1"}, {"id": 2, "code": "1234"}]
    fake = FakeB1({"clients/list": page(rows)})
    response = run(fake, "find_client", {"code": "123", "vat_code": "LT1"})
    assert response["result"]["client"]["id"] == 1
    assert fake.calls[0].body["filters"]["rules"] == [
        {"field": "code", "op": "eq", "data": "123"},
        {"field": "vatCode", "op": "eq", "data": "LT1"},
    ]
    two = FakeB1({"clients/list": page([{"id": 1, "code": "9"}, {"id": 2, "code": "9"}])})
    assert run(two, "find_client", {"code": "9"})["error_code"] == "conflict"
    assert run(FakeB1(), "find_client", {})["error_code"] == "invalid_payload"


def test_find_or_create_client_creates_only_when_nothing_matches() -> None:
    fake = FakeB1({"clients/list": page([]), "clients/create": ok({"id": 7})})
    response = run(
        fake,
        "find_or_create_client",
        {"code": "123", "email": "a@b.lt", "name": "UAB", "location_id": 1},
    )
    assert response["ok"] is True, response
    assert response["result"]["client_id"] == 7 and response["result"]["created"] is True
    assert fake.calls[1].body == {"name": "UAB", "locationId": 1, "code": "123", "email": "a@b.lt"}
    found = FakeB1({"clients/list": page([{"id": 3, "code": "123"}])})
    response = run(found, "find_or_create_client", {"code": "123", "name": "UAB", "location_id": 1})
    assert response["result"]["created"] is False and found.paths() == ["clients/list"]
    two = FakeB1({"clients/list": page([{"id": 3, "code": "1"}, {"id": 4, "code": "1"}])})
    response = run(two, "find_or_create_client", {"code": "1", "name": "U", "location_id": 1})
    assert response["error_code"] == "conflict" and two.paths() == ["clients/list"]
    missing = FakeB1()
    assert run(missing, "find_or_create_client", {"code": "1"})["error_code"] == ("invalid_payload")
    assert missing.calls == []


def test_find_or_create_item() -> None:
    fake = FakeB1(
        {"reference-book/items/list": page([]), "reference-book/items/create": ok({"id": 11})}
    )
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
    assert response["result"]["item_id"] == 11
    assert fake.calls[1].body["priceWithoutVat"] == pytest.approx(10.5)
    found = FakeB1({"reference-book/items/list": page([{"id": 5, "barcode": "475"}])})
    response = run(found, "find_item", {"barcode": "475"})
    assert response["result"]["item"]["id"] == 5


INVOICE = {
    "transaction_id": "SHOP-1001",
    "sale_date": "2026-11-16",
    "warehouse_id": 1,
    "client_id": 2,
    "operation_type_id": 3,
    "employee_id": 4,
    "lines": [
        {"item_id": 10, "quantity": "2", "price_without_vat": "10.50", "vat_rate": "21"},
        {"item_id": 11, "quantity": "1", "price_without_vat": "5"},
    ],
}


def test_a_sales_invoice_is_created_with_its_lines() -> None:
    fake = FakeB1(
        {
            "warehouse/sales/list": page([]),
            "warehouse/sales/create": ok({"id": 100}),
            "warehouse/sale-items/create-simple": [ok({"id": 1}), ok({"id": 2})],
        }
    )
    response = run(fake, "create_sales_invoice", INVOICE)
    assert response["ok"] is True, response
    assert response["result"]["sale_id"] == 100 and response["result"]["line_ids"] == [1, 2]
    assert fake.calls[0].body["filters"]["rules"] == [
        {"field": "transactionId", "op": "eq", "data": "SHOP-1001"}
    ]
    header = fake.calls[1].body
    assert header["transactionId"] == "SHOP-1001"
    assert header["autoGenerateNumberAndSeries"] is True
    assert fake.calls[2].body["saleId"] == 100 and fake.calls[3].body["itemId"] == 11


def test_a_sale_with_the_same_transaction_id_is_not_created_again() -> None:
    fake = FakeB1({"warehouse/sales/list": page([{"id": 55, "transactionId": "SHOP-1001"}])})
    response = run(fake, "create_sales_invoice", INVOICE)
    assert response["error_code"] == "conflict"
    assert response["definitely_no_external_effect"] is True
    assert fake.paths() == ["warehouse/sales/list"]


def test_a_sales_invoice_needs_a_transaction_id_and_both_series_and_number() -> None:
    fake = FakeB1()
    for bad in (
        {k: v for k, v in INVOICE.items() if k != "transaction_id"},
        {**INVOICE, "series": "S"},
        {**INVOICE, "lines": []},
        {**INVOICE, "lines": [{"item_id": 1, "quantity": "1"}]},
    ):
        assert run(fake, "create_sales_invoice", bad)["error_code"] == "invalid_payload"
    assert fake.calls == []


@pytest.mark.parametrize("failure", [refusal(400, "Item not in stock"), TimeoutError()])
def test_a_line_that_fails_reports_what_was_created(failure: Any) -> None:
    fake = FakeB1(
        {
            "warehouse/sales/list": page([]),
            "warehouse/sales/create": ok({"id": 100}),
            "warehouse/sale-items/create-simple": [ok({"id": 1}), failure],
        }
    )
    response = run(fake, "create_sales_invoice", INVOICE)
    assert response["ok"] is False
    assert response["external_effect_status"] == "timeout_unknown"
    assert response["definitely_no_external_effect"] is False
    assert "Sale 100 and 1 of its 2 lines were created (line ids [1])" in response["error"]
    assert "Nothing created was deleted" in response["error"]
    assert not any("delete" in p for p in fake.paths())


def test_a_purchase_invoice_without_discount_fills_the_required_discount_fields() -> None:
    fake = FakeB1(
        {
            "warehouse/purchases/list": page([]),
            "warehouse/purchases/create": ok({"id": 200}),
            "warehouse/purchase-items/create": ok({"id": 9}),
        }
    )
    response = run(
        fake,
        "create_purchase_invoice",
        {
            "supplier_id": 5,
            "number": "PUR-1",
            "purchase_date": "2026-11-16",
            "warehouse_id": 1,
            "operation_type_id": 2,
            "currency_id": 1,
            "employee_id": 4,
            "vat": "33.11",
            "lines": [
                {
                    "item_id": 7,
                    "quantity": "3",
                    "price_without_vat": "3.7651",
                    "price_with_vat": "4.5558",
                    "vat_rate": "21",
                }
            ],
        },
    )
    assert response["ok"] is True, response
    assert fake.calls[1].body["vat"] == 3311
    line = fake.calls[2].body
    assert (line["purchaseId"], line["position"], line["warehouseId"]) == (200, 1, 1)
    assert (
        line["quantity"],
        line["priceWithoutVat"],
        line["priceWithVat"],
        line["priceWithoutVatWithDiscount"],
        line["vatRate"],
    ) == (3000, 37651, 45558, 37651, 2100)
    assert (line["discountRate"], line["discount"], line["discountSum"]) == (0, 0, 0)
    dupe = FakeB1({"warehouse/purchases/list": page([{"id": 9, "clientId": 5, "number": "PUR-1"}])})
    again = run(
        dupe,
        "create_purchase_invoice",
        {
            "supplier_id": 5,
            "number": "PUR-1",
            "purchase_date": "2026-11-16",
            "warehouse_id": 1,
            "operation_type_id": 2,
            "currency_id": 1,
            "employee_id": 4,
            "lines": [
                {
                    "item_id": 7,
                    "quantity": "3",
                    "price_without_vat": "1",
                    "price_with_vat": "1.21",
                    "vat_rate": "21",
                }
            ],
        },
    )
    assert again["error_code"] == "conflict"


def test_a_payment_is_checked_for_repeats_and_sent_in_cents() -> None:
    inputs = {
        "sale_id": 100,
        "payment_id": "PAY-1",
        "payment_date": "2026-11-16",
        "amount": "25.41",
        "tax": "0.63",
        "currency": "EUR",
        "purpose": "Invoice S-1",
    }
    fake = FakeB1(
        {
            "bank/transactions/list": page([]),
            "bank/sale-invoice/payment": ok({"transactionId": 321}),
        }
    )
    response = run(fake, "record_sale_payment", inputs)
    assert response["ok"] is True, response
    assert fake.calls[1].body["sum"] == 2541 and fake.calls[1].body["tax"] == 63
    assert response["result"]["transaction_id"] == "321"
    seen = FakeB1({"bank/transactions/list": page([{"id": 8, "number": "PAY-1"}])})
    again = run(seen, "record_sale_payment", inputs)
    assert again["error_code"] == "conflict" and seen.paths() == ["bank/transactions/list"]
    assert (
        run(FakeB1(), "record_sale_payment", {**inputs, "amount": "1.001"})["error_code"]
        == "invalid_payload"
    )


def test_find_sale() -> None:
    fake = FakeB1({"warehouse/sales/list": page([{"id": 1, "series": "S", "number": "1"}])})
    assert run(fake, "find_sale", {"series": "S", "number": "1"})["result"]["found"] is True
    assert run(FakeB1(), "find_sale", {"series": "S"})["error_code"] == "invalid_payload"


def test_get_report_waits_for_the_file(monkeypatch: Any) -> None:
    monkeypatch.setattr(composites, "REPORT_POLL_SECONDS", 0.0)
    files = Files()
    fake = FakeB1(
        {
            "reports/general-ledger-general-ledger/trial-balance": {"code": 200, "taskId": 5},
            "reports/get": [refusal(400, "Not ready"), file(b"PK\x03\x04", "tb.xlsx")],
        }
    )
    from runtime import generic

    entry = generic.spec("reports_general_ledger_general_ledger_trial_balance")
    parameters = {
        n["name"]: {"text": "2026-01-01", "decimal": "1", "integer": 1, "boolean": True}.get(
            n["kind"], []
        )
        for n in entry["params"]
        if n.get("required")
    }
    response = run(
        fake,
        "get_report",
        {"report": "reports_general_ledger_general_ledger_trial_balance", "parameters": parameters},
        files=files,
    )
    assert response["ok"] is True, response
    assert response["result"]["ready"] is True and response["result"]["file"] == "art_1"
    assert fake.paths().count("reports/get") == 2
    assert run(FakeB1(), "get_report", {"report": "clients_list"})["error_code"] == (
        "invalid_payload"
    )


def test_test_mode_runs_no_everyday_write() -> None:
    fake = FakeB1()
    for operation, inputs in (
        ("create_sales_invoice", INVOICE),
        ("find_or_create_client", {"code": "1", "name": "U", "location_id": 1}),
    ):
        response = run(fake, operation, inputs, test_mode=True)
        assert response["ok"] is True and response["definitely_no_external_effect"] is True
    assert fake.calls == []
