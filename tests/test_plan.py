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


def test_every_endpoint_is_a_step_of_this_release() -> None:
    by = collections.Counter((r["kind"], r["danger"]) for r in ROWS)
    assert all(r["release"] == "0.1.0" and r["reason"] for r in ROWS)
    assert by[("delete", "delete")] == 117
    assert sum(n for (k, d), n in by.items() if d == "irreversible") == 23
    for row in ROWS:
        if row["kind"] == "delete":
            assert row["danger"] == "delete", row["path"]
        if row["path"].startswith("salary/") and row["kind"] in plan.WRITE_KINDS - {"delete"}:
            assert row["danger"] == "irreversible", row["path"]
    for path in plan.IRREVERSIBLE_ACTIONS:
        row = next(r for r in ROWS if r["path"] == path)
        assert row["danger"] == "irreversible" and row["kind"] in {"action", "action_file"}
    # Not confirmed to be a read: generate-ffdata is a write with an effect.
    ffdata = next(r for r in ROWS if r["path"] == "declaration/generations/generate-ffdata")
    assert ffdata["kind"] == "action_file"
    for row in ROWS:
        if row["kind"] in {"read", "file", "report", "report_get"}:
            assert row["danger"] == "" and row["objects"] == "", row["path"]
    writes = {r["path"] for r in ROWS if r["kind"] in plan.WRITE_KINDS}
    assert set(plan.EVERYDAY_WRITES) <= writes and len(writes) == 346


def test_known_ids_of_later_releases_are_fixed_now() -> None:
    ids = {r["path"]: r["operation_id"] for r in ROWS}
    assert ids["warehouse/sales/delete"] == "warehouse_sales_delete"
    assert ids["salary/payrolls/create"] == "salary_payrolls_create"
    assert ids["general-ledger/settlements/settle"] == "general_ledger_settlements_settle"
    assert ids["declaration/generations/generate-ffdata"] == (
        "declaration_generations_generate_ffdata"
    )
