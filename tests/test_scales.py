"""Amounts the API takes or gives "multiplied by N": every one of them, both ways."""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from typing import Any

import pytest
from support import BUNDLE, FakeB1, page, run

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import params as reference_params  # noqa: E402

from runtime import params  # noqa: E402

FACTS = json.loads((BUNDLE / "tests" / "reference" / "b1_api.json").read_text())["endpoints"]
SENT = [(e["path"], p["field"], p["scale"]) for e in FACTS for p in e["params"] if p.get("scale")]
READ = [(e["path"], a["field"], a["scale"]) for e in FACTS for a in e["answer"] if a.get("scale")]


def test_all_scaled_fields_are_known() -> None:
    assert len(SENT) + len(READ) == 53
    assert {s for _, _, s in SENT + READ} == {100, 1000, 10000, 1000000}


def _node(path: str, field: str) -> dict[str, Any]:
    entry = next(e for e in FACTS if e["path"] == path)
    nodes = reference_params.tree(
        entry["params"], skip=reference_params.LIST_PARAMS if entry["rows"] else frozenset()
    )
    parts = field.split(".")
    node = next(n for n in nodes if n["name"] == parts[0])
    for part in parts[1:]:
        node = next(n for n in node["children"] if n["name"] == part)
    return node


@pytest.mark.parametrize(("path", "field", "scale"), SENT, ids=[f"{p}:{f}" for p, f, _ in SENT])
def test_every_scaled_input_is_sent_multiplied(path: str, field: str, scale: int) -> None:
    node = _node(path, field)
    assert node["scale"] == scale
    wire = (lambda n: str(n)) if node.get("as_text") else (lambda n: n)
    assert params.check(node, Decimal("1.5"), field) == wire(int(Decimal("1.5") * scale))
    assert params.check(node, "3", field) == wire(3 * scale)
    assert params.check(node, Decimal("0"), field) == wire(0)
    # One decimal more than the scale allows is refused, never rounded.
    finer = Decimal(1) / (scale * 10)
    with pytest.raises(Exception) as caught:
        params.check(node, finer, field)
    assert getattr(caught.value, "code", "") == "invalid_payload"


@pytest.mark.parametrize(("path", "field", "scale"), READ, ids=[f"{p}:{f}" for p, f, _ in READ])
def test_every_scaled_answer_is_read_back_as_a_decimal(path: str, field: str, scale: int) -> None:
    name = field.split(".", 1)[1]
    raw = {"id": 1, name: 12345, "untouched": 12345}
    [row] = params.unscale([raw], {field: scale}, "data")
    assert row[name] == format(Decimal(12345) / scale, "f")
    assert row["untouched"] == 12345


def test_cash_register_sales_are_listed_in_plain_amounts() -> None:
    fake = FakeB1(
        {
            "cash-register/sales/list": page(
                [{"id": 1, "total": 2541, "vat": 441, "paidWithCard": 2541, "number": 7}]
            )
        }
    )
    response = run(fake, "cash_register_sales_list", {"rows": 10})
    [item] = response["result"]["items"]
    assert (item["total"], item["vat"], item["paidWithCard"]) == ("25.41", "4.41", "25.41")
    assert item["number"] == 7


def test_purchase_lines_are_listed_as_sent_when_no_scale_is_documented() -> None:
    fake = FakeB1(
        {
            "warehouse/purchase-items/list": page(
                [{"id": 1, "quantity": 3000, "priceWithoutVat": 37651}]
            )
        }
    )
    response = run(fake, "warehouse_purchase_items_list", {"rows": 10})
    [item] = response["result"]["items"]
    assert item["quantity"] == 3000 and item["priceWithoutVat"] == 37651


def test_a_purchase_line_reaches_the_wire_in_the_documented_units() -> None:
    fake = FakeB1({"warehouse/purchase-items/create": {"code": 200, "data": {"id": 9}}})
    response = run(
        fake,
        "warehouse_purchase_items_create",
        {
            "purchaseId": 1,
            "position": 1,
            "warehouseId": 2,
            "itemId": 3,
            "quantity": "3",
            "vatRate": "21",
            "priceWithoutVat": "3.7651",
            "priceWithVat": "4.4190",
            "priceWithoutVatWithDiscount": "3.7651",
            "discountRate": "3",
            "discount": "0.34",
            "discountSum": "0.34",
        },
    )
    assert response["ok"] is True, response
    body = fake.calls[0].body
    assert (
        body["quantity"],
        body["vatRate"],
        body["priceWithoutVat"],
        body["priceWithVat"],
        body["discountRate"],
        body["discount"],
        body["discountSum"],
    ) == (3000, 2100, 37651, 44190, 3000, 340000, 3400)
    # A sale line takes plain decimals: sent as given.
    sale = FakeB1({"warehouse/sale-items/create-simple": {"code": 200, "data": {"id": 5}}})
    run(
        sale,
        "warehouse_sale_items_create_simple",
        {"saleId": 1, "itemId": 3, "quantity": "3", "priceWithoutVat": "145.12"},
    )
    assert sale.calls[0].body["priceWithoutVat"] == Decimal("145.12")


def test_a_shop_order_in_cents() -> None:
    fake = FakeB1({"shop/orders/add": {"code": 200, "data": {"id": 1}}})
    response = run(
        fake,
        "shop_orders_add",
        {
            "prefix": "wn55tg",
            "orderId": 1,
            "orderDate": "2026-11-16",
            "orderNo": "1",
            "currency": "EUR",
            "discount": "10.10",
            "total": "500.10",
            "billing": {"name": "UAB", "isCompany": 1, "country": "LT"},
            "delivery": {"isCompany": 1, "country": "LT"},
            "items": [{"name": "A", "quantity": "3", "price": "3.10", "sum": "9.30"}],
        },
    )
    assert response["ok"] is True, response
    body = fake.calls[0].body
    assert (body["discount"], body["total"]) == (1010, 50010)
    assert body["items"][0] == {"name": "A", "quantity": 300, "price": 310, "sum": 930}
    with_payment = FakeB1({"shop/orders/add": {"code": 200, "data": {"id": 1}}})
    run(
        with_payment,
        "shop_orders_add",
        {
            "prefix": "wn55tg",
            "orderId": 1,
            "orderDate": "2026-11-16",
            "orderNo": "1",
            "currency": "EUR",
            "discount": "0",
            "total": "333.10",
            "billing": {"name": "UAB", "isCompany": 1, "country": "LT"},
            "delivery": {"isCompany": 1, "country": "LT"},
            "items": [{"name": "A", "quantity": "1", "price": "333.10", "sum": "333.10"}],
            "payment": {
                "code": "BANK",
                "id": "SB0910144RGT",
                "paymentDate": "2026-11-16",
                "sum": "333.10",
                "currency": "EUR",
            },
        },
    )
    # payment.sum is typed String in the documentation: the whole number goes as text.
    assert with_payment.calls[0].body["payment"]["sum"] == "33310"
