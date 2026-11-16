"""Deletions and the irreversible accounting actions: explicit IDs, no retries, honest outcomes."""

from __future__ import annotations

from typing import Any

import pytest
from support import FakeB1, Files, file, ok, refusal, run

from runtime import catalog, generic

UNKNOWN = "timeout_unknown"


def _unknown(response: dict[str, Any]) -> bool:
    return (
        response.get("ok") is not True
        and response["definitely_no_external_effect"] is False
        and response["external_effect_status"] == UNKNOWN
    )


def _no_effect(response: dict[str, Any]) -> bool:
    return response.get("ok") is not True and response["definitely_no_external_effect"] is True


# -- deletions by a list of IDs ---------------------------------------------------------------


def test_a_deletion_sends_exactly_the_given_ids_and_says_which() -> None:
    fake = FakeB1({"warehouse/sales/delete": ok(None, message="Deleted")})
    response = run(fake, "warehouse_sales_delete", {"ids": [5, "7"]})
    assert response["ok"] is True, response
    assert fake.calls[0].body == {"ids": [5, 7]}
    assert response["result"]["sent_ids"] == [5, 7]
    assert response["result"]["message"] == "Deleted"
    assert response["external_effect_status"] == "succeeded"


@pytest.mark.parametrize(
    "ids",
    [
        [],
        [0],
        [-1],
        [1.5],
        ["1-5"],
        ["*"],
        ["all"],
        [True],
        [None],
        [3, 3],
        list(range(1, 52)),
        "1,2",
        5,
        {"from": 1, "to": 9},
        [10**16],
    ],
)
def test_a_deletion_takes_only_a_short_list_of_distinct_positive_ids(ids: Any) -> None:
    fake = FakeB1()
    response = run(fake, "warehouse_sales_delete", {"ids": ids})
    assert response["error_code"] == "invalid_payload", ids
    assert _no_effect(response)
    assert fake.calls == []


def test_a_deletion_takes_no_filter_or_other_field() -> None:
    fake = FakeB1()
    for given in (
        {"ids": [1], "filters": [{"field": "id", "op": "gt", "data": "0"}]},
        {"filters": [{"field": "id", "op": "gt", "data": "0"}]},
        {},
        {"ids": [1], "all": True},
    ):
        assert run(fake, "warehouse_sales_delete", given)["error_code"] == "invalid_payload"
    assert fake.calls == []


def test_fifty_ids_are_the_most_one_run_deletes() -> None:
    fake = FakeB1({"warehouse/sales/delete": ok()})
    response = run(fake, "warehouse_sales_delete", {"ids": list(range(1, 51))})
    assert response["ok"] is True
    assert len(fake.calls[0].body["ids"]) == 50


def test_a_deletion_in_a_test_run_sends_nothing() -> None:
    fake = FakeB1()
    response = run(fake, "warehouse_sales_delete", {"ids": [1, 2]}, test_mode=True)
    assert response["ok"] is True
    assert response["result"]["sent_ids"] == []
    assert response["definitely_no_external_effect"] is True
    assert response["external_effect_status"] == "failed"
    assert fake.calls == []


@pytest.mark.parametrize("status", [401, 403])
def test_a_refused_key_deleted_nothing(status: int) -> None:
    fake = FakeB1({"warehouse/sales/delete": refusal(status)})
    assert _no_effect(run(fake, "warehouse_sales_delete", {"ids": [1, 2]}))


def test_a_400_proves_nothing_was_deleted_only_for_one_id() -> None:
    one = FakeB1({"warehouse/sales/delete": refusal(400)})
    assert _no_effect(run(one, "warehouse_sales_delete", {"ids": [1]}))
    several = FakeB1({"warehouse/sales/delete": refusal(400)})
    assert _unknown(run(several, "warehouse_sales_delete", {"ids": [1, 2]}))


@pytest.mark.parametrize("status", [404, 409, 429, 480, 500, 503])
def test_any_other_refusal_of_a_deletion_is_unknown_and_not_retried(status: int) -> None:
    fake = FakeB1({"warehouse/sales/delete": [refusal(status), ok()]})
    response = run(fake, "warehouse_sales_delete", {"ids": [1]})
    assert _unknown(response), status
    assert len(fake.calls) == 1


def test_a_refusal_inside_a_200_answer_is_unknown() -> None:
    fake = FakeB1({"warehouse/sales/delete": {"code": 400, "message": "Some were not deleted"}})
    assert _unknown(run(fake, "warehouse_sales_delete", {"ids": [1, 2]}))


def test_a_timeout_of_a_deletion_is_unknown() -> None:
    fake = FakeB1({"warehouse/sales/delete": TimeoutError()})
    assert _unknown(run(fake, "warehouse_sales_delete", {"ids": [1]}))


# -- the other deletion shapes ----------------------------------------------------------------


def test_a_deletion_of_one_record_by_its_id() -> None:
    fake = FakeB1({"bank/transaction-files/delete": [ok(), refusal(400)]})
    assert run(fake, "bank_transaction_files_delete", {"id": 9})["result"]["sent_ids"] == [9]
    assert fake.calls[0].body == {"id": 9}
    assert _no_effect(run(fake, "bank_transaction_files_delete", {"id": 9}))
    for bad in (0, -2, "x", 2.5, [9]):
        assert (
            run(FakeB1(), "bank_transaction_files_delete", {"id": bad})["error_code"]
            == "invalid_payload"
        ), bad


def test_a_deletion_of_records_named_by_two_ids() -> None:
    fake = FakeB1({"production/bundle-debundle-products/delete": ok()})
    pair = {"productionId": 1, "mainProductionId": 2}
    response = run(fake, "production_bundle_debundle_products_delete", {"ids": [pair]})
    assert response["result"]["sent_ids"] == [pair]
    for bad in (
        [pair, dict(pair)],
        [{"productionId": 1}],
        [{**pair, "extra": 1}],
        [{"productionId": 0, "mainProductionId": 2}],
        [pair] * 51,
    ):
        response = run(FakeB1(), "production_bundle_debundle_products_delete", {"ids": bad})
        assert response["error_code"] == "invalid_payload", bad


def test_a_deletion_documented_with_one_object_of_ids_takes_one() -> None:
    entry = generic.spec("bank_transaction_entries_delete")
    assert entry["max_ids"] == 1 and entry["objects"] == "one"
    fake = FakeB1({"bank/transaction-entries/delete": refusal(400)})
    response = run(fake, "bank_transaction_entries_delete", {"ids": {"id": 4}})
    assert fake.calls[0].body == {"ids": {"id": 4}}
    assert _no_effect(response)


def test_an_e_commerce_order_deletion_names_the_shop_and_the_order() -> None:
    fake = FakeB1({"e-commerce/orders/delete": ok()})
    response = run(fake, "e_commerce_orders_delete", {"shopId": "eshop", "internalId": 77})
    assert fake.calls[0].body == {"shopId": "eshop", "internalId": 77}
    assert response["result"]["sent_ids"] == [{"shopId": "eshop", "internalId": 77}]


def test_every_deletion_checks_its_ids_and_sends_nothing_in_a_test_run() -> None:
    for oid, entry in generic.registry().items():
        if entry["kind"] != "delete":
            continue
        assert oid in catalog.EFFECT_OPERATION_IDS
        fake = FakeB1()
        assert run(fake, oid, {})["error_code"] == "invalid_payload", oid
        assert run(fake, oid, {}, test_mode=True)["error_code"] == "invalid_payload", oid
        assert fake.calls == [], oid


# -- irreversible accounting actions ----------------------------------------------------------


def test_settling_is_several_objects_so_a_400_is_unknown() -> None:
    fake = FakeB1({"general-ledger/settlements/settle": refusal(400)})
    response = run(fake, "general_ledger_settlements_settle", {"settlementIds": [[1, 2], [3, 4]]})
    assert fake.calls[0].body == {"settlementIds": [[1, 2], [3, 4]]}
    assert _unknown(response)


def test_confirming_movements_is_several_objects() -> None:
    fake = FakeB1({"warehouse/internal-movements/confirm": refusal(400)})
    assert _unknown(run(fake, "warehouse_internal_movements_confirm", {"ids": [1]}))


def test_a_link_of_one_article_trusts_a_400_but_not_a_409() -> None:
    inputs = {"articleId": 1, "correspondenceAccountId": 2}
    assert _no_effect(
        run(
            FakeB1({"general-ledger/financial-accountability-articles/link": refusal(400)}),
            "general_ledger_financial_accountability_articles_link",
            inputs,
        )
    )
    assert _unknown(
        run(
            FakeB1({"general-ledger/financial-accountability-articles/link": refusal(409)}),
            "general_ledger_financial_accountability_articles_link",
            inputs,
        )
    )


@pytest.mark.parametrize(
    ("oid", "path", "inputs"),
    [
        (
            "warehouse_purchases_calculate_overhead_costs",
            "warehouse/purchases/calculate-overhead-costs",
            {"id": 1},
        ),
        (
            "warehouse_purchases_reset_overhead_costs",
            "warehouse/purchases/reset-overhead-costs",
            {"id": 1},
        ),
        (
            "warehouse_stock_taking_generate",
            "warehouse/stock-taking/generate",
            {"stockTakingId": 1},
        ),
        (
            "e_commerce_orders_create_write_off",
            "e-commerce/orders/create-write-off",
            {"orderId": 1},
        ),
    ],
)
def test_actions_that_change_several_records_trust_no_400(
    oid: str, path: str, inputs: dict[str, Any]
) -> None:
    fake = FakeB1({path: [refusal(400), ok()]})
    assert _unknown(run(fake, oid, inputs))
    assert len(fake.calls) == 1
    assert run(FakeB1(), oid, inputs, test_mode=True)["definitely_no_external_effect"] is True


def test_a_declaration_file_is_a_write_that_returns_the_file() -> None:
    oid = "declaration_generations_generate_ffdata"
    assert oid in catalog.EFFECT_OPERATION_IDS and oid in catalog.FILE_OUTPUT_IDS
    files = Files()
    fake = FakeB1(
        {
            "declaration/generations/generate-ffdata": file(
                b"<FFData/>", "FR0600.ffdata", "application/xml"
            )
        }
    )
    response = run(
        fake,
        oid,
        {"templateId": 6, "dateFrom": "2026-01-01", "dateTill": "2026-01-31"},
        files=files,
    )
    assert response["ok"] is True, response
    assert response["result"]["file_name"] == "FR0600.ffdata"
    assert response["external_effect_status"] == "succeeded"
    assert files.written[0]["data"] == b"<FFData/>"
    nothing = FakeB1()
    test_run = run(nothing, oid, {"templateId": 6}, test_mode=True)
    assert test_run["result"]["file"] is None and nothing.calls == []


def test_a_declaration_answered_without_a_file_is_unknown() -> None:
    fake = FakeB1({"declaration/generations/generate-ffdata": ok({"x": 1})})
    assert _unknown(run(fake, "declaration_generations_generate_ffdata", {"templateId": 6}))


def test_a_declaration_whose_file_cannot_be_saved_is_unknown() -> None:
    fake = FakeB1(
        {"declaration/generations/generate-ffdata": file(b"<FFData/>", "a.ffdata", "text/xml")}
    )
    response = run(
        fake, "declaration_generations_generate_ffdata", {"templateId": 6}, files=Files(fail=True)
    )
    assert _unknown(response)


def test_a_salary_write_does_not_trust_a_409() -> None:
    entry = generic.spec("salary_departments_create")
    assert entry["strict"] is True
    sample = {"text": "X", "decimal": "1", "integer": 1, "boolean": True}
    required = {n["name"]: sample[n["kind"]] for n in entry["params"] if n.get("required")}
    fake = FakeB1({"salary/departments/create": refusal(409)})
    assert _unknown(run(fake, "salary_departments_create", required))


def test_an_ordinary_create_still_trusts_a_409() -> None:
    fake = FakeB1({"clients/create": refusal(409)})
    response = run(fake, "clients_create", {"name": "A", "locationId": 1})
    assert response["error_code"] == "conflict" and _no_effect(response)


# -- every write ------------------------------------------------------------------------------


def test_no_write_sends_anything_in_a_test_run() -> None:
    writes = sorted(catalog.EFFECT_OPERATION_IDS & catalog.GENERATED_IDS)
    assert len(writes) == 346
    for oid in writes:
        fake = FakeB1()
        response = run(fake, oid, {}, test_mode=True)
        assert fake.calls == [], oid
        assert response["definitely_no_external_effect"] is True, oid
