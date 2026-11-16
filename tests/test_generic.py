"""Generated steps: lists, reads, files, reports, writes and uploads."""

from __future__ import annotations

from typing import Any

import pytest
from support import API_KEY, FakeB1, Files, file, ok, page, run

from runtime import generic


def test_a_list_sends_rows_cursor_sort_and_filters() -> None:
    fake = FakeB1(
        {"clients/list": page([{"id": 1, "code": "123"}], nextCursor="abc", hasMore=True)}
    )
    response = run(
        fake,
        "clients_list",
        {
            "rows": 50,
            "cursor": "prev",
            "sidx": "name",
            "sord": "desc",
            "filters": [
                {"field": "code", "op": "eq", "data": "123"},
                {"field": "email", "op": "nn"},
            ],
        },
    )
    assert response["ok"] is True, response
    assert fake.calls[0].body == {
        "rows": 50,
        "cursor": "prev",
        "sidx": "name",
        "sord": "desc",
        "filters": {
            "groupOp": "AND",
            "rules": [
                {"field": "code", "op": "eq", "data": "123"},
                {"field": "email", "op": "nn", "data": ""},
            ],
        },
    }
    result = response["result"]
    assert result["items"] == [{"id": 1, "code": "123"}]
    assert (result["next_cursor"], result["has_more"], result["count"]) == ("abc", True, 1)


def test_a_list_takes_100_rows_by_default_and_pages_where_documented() -> None:
    fake = FakeB1({"warehouse/sales/list": page([])})
    run(fake, "warehouse_sales_list", {"page": 3})
    assert fake.calls[0].body == {"rows": 100, "page": 3}


@pytest.mark.parametrize(
    "bad",
    [
        {"rows": 7},
        {"rows": 1000},
        {"sidx": "password"},
        {"sord": "up"},
        {"filters": [{"field": "secret", "op": "eq", "data": "x"}]},
        {"filters": [{"field": "code", "op": "like", "data": "x"}]},
        {"filters": [{"field": "code", "op": "eq", "data": "x", "extra": 1}]},
        {"filters": [{"field": "code", "op": "eq", "data": {"a": 1}}]},
        {"page": 2},
        {"colour": "red"},
    ],
)
def test_list_inputs_are_checked_before_anything_is_asked(bad: dict[str, Any]) -> None:
    fake = FakeB1()
    response = run(fake, "clients_list", bad)
    assert response["error_code"] == "invalid_payload", response
    assert fake.calls == []


def test_a_cursor_and_a_page_together_are_refused() -> None:
    fake = FakeB1()
    assert (
        run(fake, "reference_book_items_list", {"cursor": "a", "page": 2})["error_code"]
        == "invalid_payload"
    )


def test_a_list_too_large_for_the_output_is_refused_with_a_hint(monkeypatch: Any) -> None:
    from runtime import budget

    monkeypatch.setattr(budget, "MAX_CANDIDATE_STRINGS", 5)
    rows = [{"id": n, "name": f"N{n}", "code": f"C{n}"} for n in range(5)]
    response = run(FakeB1({"clients/list": page(rows)}), "clients_list", {"rows": 10})
    assert response["error_code"] == "response_too_large"


def test_a_file_is_saved_as_a_workflow_file() -> None:
    files = Files()
    fake = FakeB1({"warehouse/invoices/get-sale": file(b"%PDF-1.7 x", "S-1.pdf")})
    response = run(fake, "warehouse_invoices_get_sale", {"series": "S", "number": "1"}, files=files)
    assert response["ok"] is True, response
    assert response["result"] == {
        "file": "art_1",
        "file_name": "S-1.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 10,
        "warnings": [],
    }
    assert files.written[0]["binding_key"] == "b1_file"
    assert fake.calls[0].body == {"series": "S", "number": "1"}


def test_a_file_step_answered_with_json_is_a_refusal() -> None:
    fake = FakeB1({"warehouse/invoices/get-sale": {"code": 404, "message": "Not found"}})
    response = run(fake, "warehouse_invoices_get_sale", {"series": "S", "number": "1"})
    assert response["error_code"] == "not_found"
    assert response["definitely_no_external_effect"] is True


def test_a_report_returns_its_task_and_the_file_comes_later() -> None:
    fake = FakeB1(
        {"reports/general-ledger-general-ledger/trial-balance": {"code": 200, "taskId": 77}}
    )
    entry = generic.spec("reports_general_ledger_general_ledger_trial_balance")
    required = {n["name"]: _sample(n) for n in entry["params"] if n.get("required")}
    response = run(fake, "reports_general_ledger_general_ledger_trial_balance", required)
    assert response["ok"] is True, response
    assert response["result"]["task_id"] == 77
    later = FakeB1({"reports/get": file(b"PK\x03\x04", "tb.xlsx", "application/vnd.ms-excel")})
    got = run(later, "reports_get", {"taskId": 77})
    assert got["result"]["file_name"] == "tb.xlsx"


def _sample(node: dict[str, Any]) -> Any:
    return {
        "text": "2026-01-01",
        "decimal": "1",
        "integer": 1,
        "boolean": True,
        "decimal_list": [1],
        "json": [],
        "object": {},
        "object_list": [],
    }[node["kind"]]


def test_a_read_returns_data() -> None:
    fake = FakeB1({"client/sales/balance": ok({"balance": 10})})
    entry = generic.spec("client_sales_balance")
    required = {n["name"]: _sample(n) for n in entry["params"] if n.get("required")}
    response = run(fake, "client_sales_balance", required)
    assert response["result"]["data"] == {"balance": 10}


def test_a_write_refuses_unknown_and_missing_fields_before_sending() -> None:
    fake = FakeB1()
    assert run(fake, "clients_create", {"locationId": 1})["error_code"] == "invalid_payload"
    assert (
        run(fake, "clients_create", {"name": "A", "locationId": 1, "extra": 1})["error_code"]
        == "invalid_payload"
    )
    assert (
        run(fake, "clients_create", {"name": "A", "locationId": "x"})["error_code"]
        == "invalid_payload"
    )
    assert fake.calls == []


def test_test_mode_checks_and_sends_nothing() -> None:
    fake = FakeB1()
    response = run(fake, "clients_create", {"name": "A", "locationId": 1}, test_mode=True)
    assert response["ok"] is True
    assert response["definitely_no_external_effect"] is True
    assert (
        run(fake, "clients_create", {"locationId": 1}, test_mode=True)["error_code"]
        == "invalid_payload"
    )
    assert fake.calls == []


def test_an_upload_sends_the_bytes_with_its_headers() -> None:
    files = Files(content=b"%PDF-1.4 attach")
    fake = FakeB1({"warehouse/sale-files/create": ok({"id": 3})})
    response = run(
        fake,
        "warehouse_sale_files_create",
        {
            "recordId": 12,
            "fileName": "invoice.pdf",
            "file": "art_9",
            "content_type": "application/pdf",
        },
        files=files,
    )
    assert response["ok"] is True, response
    call = fake.calls[0]
    assert call.raw_body == b"%PDF-1.4 attach"
    assert call.headers["b1-id"] == "12"
    assert call.headers["b1-file-name"] == "invoice.pdf"
    assert call.headers["content-type"] == "application/pdf"
    assert call.headers["b1-api-key"] == API_KEY
    assert response["result"]["id"] == 3
    bad = run(
        FakeB1(),
        "warehouse_sale_files_create",
        {"recordId": 12, "fileName": "sąskaita.pdf", "file": "art_9"},
    )
    assert bad["error_code"] == "invalid_payload"


def test_every_step_is_routable() -> None:
    from runtime import catalog

    assert len(catalog.OPERATION_IDS) == 610
    assert catalog.GENERATED_IDS == set(generic.registry())
