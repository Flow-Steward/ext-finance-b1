"""The step id, title and release of every one of the documented endpoints."""

from __future__ import annotations

import collections
import json
import sys

import pytest
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import plan  # noqa: E402

ROWS = plan.plan()
VERBS = {
    "List",
    "Get",
    "Create",
    "Update",
    "Delete",
    "Upload",
    "Generate",
    "Record",
    "Add",
    "Confirm",
    "Settle",
    "Set",
    "Link",
    "Calculate",
    "Reset",
}


def test_every_documented_endpoint_is_planned_once() -> None:
    facts = json.loads((BUNDLE / "tests" / "reference" / "b1_api.json").read_text())
    assert len(ROWS) == len(facts["endpoints"]) == 600
    assert len({r["path"] for r in ROWS}) == 600


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["path"])
def test_operation_ids_follow_the_path_rule(row: dict) -> None:
    assert row["operation_id"] == row["path"].replace("/", "_").replace("-", "_")


def test_operation_ids_and_titles_are_unique() -> None:
    assert len({r["operation_id"] for r in ROWS}) == 600
    assert len({r["title"] for r in ROWS}) == 600


@pytest.mark.parametrize("row", ROWS, ids=lambda r: r["path"])
def test_titles_start_with_a_verb_and_carry_no_prefix(row: dict) -> None:
    assert row["title"].split()[0] in VERBS, row["title"]
    assert "Advanced" not in row["title"] and "·" not in row["title"]


def test_reports_are_generated_and_their_file_got() -> None:
    reports = [r for r in ROWS if r["path"].startswith("reports/")]
    assert len(reports) == 82
    for row in reports:
        if row["path"] == "reports/get":
            assert row["title"] == "Get a generated report file"
        else:
            assert row["title"].startswith("Generate the ") and row["title"].endswith(" report")


def test_releases() -> None:
    by = collections.Counter((r["release"], r["kind"]) for r in ROWS)
    released = [r for r in ROWS if r["release"] == "0.1.0"]
    assert len(released) == 287
    # Every read, file download and report ships now.
    for row in ROWS:
        if row["kind"] in {"read", "file", "report", "report_get"}:
            assert row["release"] == "0.1.0", row["path"]
    # Deletions, salary writes and irreversible actions only after a live check.
    assert by[("after-live", "delete")] == 117
    for row in ROWS:
        if row["kind"] == "delete" or (
            row["path"].startswith("salary/") and row["kind"] not in {"read", "file"}
        ):
            assert row["release"] == "after-live", row["path"]
    for path in plan.AFTER_LIVE_ACTIONS:
        assert next(r for r in ROWS if r["path"] == path)["release"] == "after-live", path
    # The everyday writes, and only those, ship among the writes.
    writes = {r["path"] for r in released if r["kind"] in {"create", "update", "upload"}}
    assert writes == set(plan.EVERYDAY_WRITES)
    assert all(r["reason"] for r in ROWS)


def test_known_ids_of_later_releases_are_fixed_now() -> None:
    ids = {r["path"]: r["operation_id"] for r in ROWS}
    assert ids["warehouse/sales/delete"] == "warehouse_sales_delete"
    assert ids["salary/payrolls/create"] == "salary_payrolls_create"
    assert ids["general-ledger/settlements/settle"] == "general_ledger_settlements_settle"
    assert ids["declaration/generations/generate-ffdata"] == (
        "declaration_generations_generate_ffdata"
    )
