"""The generated contracts match their sources; forms, inputs and the runtime agree."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import struct
import sys
from typing import Any

import pytest
import yaml
from support import BUNDLE

sys.path.insert(0, str(BUNDLE / "tests" / "reference"))

import build_contracts  # noqa: E402
import plan  # noqa: E402

from runtime import catalog, composites, generic  # noqa: E402
from runtime.connection import CONFIG_FIELDS, SECRET_FIELDS  # noqa: E402

OUTPUTS = build_contracts.outputs()


def load(path: str) -> Any:
    return yaml.safe_load((BUNDLE / path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted(p for p in OUTPUTS if "/" in p))
def test_generated_files_are_current(path: str) -> None:
    assert (BUNDLE / path).read_text(encoding="utf-8") == build_contracts.render(
        path, OUTPUTS[path]
    ), f"{path} drifted: run python3 tests/reference/build_contracts.py"


def test_the_registry_is_every_documented_endpoint() -> None:
    rows = {r["operation_id"]: r for r in plan.plan()}
    assert len(rows) == 600
    assert set(generic.registry()) == set(rows)
    for oid, entry in generic.registry().items():
        assert entry["path"] == rows[oid]["path"]
        assert entry["kind"] == rows[oid]["kind"]


def test_every_step_is_registered_once_and_routable() -> None:
    ops = load("contracts/operation_manifest.yaml")["operations"]
    ids = [o["operation_id"] for o in ops]
    assert len(ids) == len(set(ids)) == len(catalog.OPERATION_IDS) == 610
    assert set(ids) == set(catalog.OPERATION_IDS)
    assert not set(composites.COMPOSITES) & set(generic.registry())
    titles = [o["display_name"] for o in ops]
    assert len(titles) == len(set(titles))


def test_effects_are_the_writes() -> None:
    manifest = load("extension.yaml")
    assert manifest["external_effects"] == OUTPUTS["external_effects"]
    effects = {e["operation_id"] for e in manifest["external_effects"]}
    assert effects == set(catalog.EFFECT_OPERATION_IDS)
    for op in load("contracts/operation_manifest.yaml")["operations"]:
        assert (op["operation_kind"] == "action") == (op["operation_id"] in effects)


def test_every_form_field_is_an_input_and_the_runtime_takes_it() -> None:
    forms = {f["operation_id"]: f for f in load("contracts/step_ui_manifest.yaml")["forms"]}
    for op in load("contracts/operation_manifest.yaml")["operations"]:
        oid = op["operation_id"]
        inputs = {i["name"] for i in op["inputs"]} - {"connection_ref"}
        assert {f["name"] for f in forms[oid]["fields"]} == inputs, oid
        if oid in composites.INPUTS:
            assert set(composites.INPUTS[oid]) == inputs, oid
            continue
        entry = generic.registry()[oid]
        if entry["kind"] == "upload":
            taken = {h["input"] for h in entry["headers"]} | {"file", "content_type"}
        else:
            taken = {n["name"] for n in entry["params"]}
            if entry.get("list"):
                taken |= {"rows", "sord"} | ({"cursor"} if entry["list"]["cursor"] else set())
                taken |= {"page"} if entry["list"]["page"] else set()
                taken |= {"sidx", "filters"} if entry["list"]["fields"] else set()
        assert inputs == taken, oid


def test_every_step_declares_warnings() -> None:
    for op in load("contracts/operation_manifest.yaml")["operations"]:
        assert "warnings" in [o["name"] for o in op["outputs"]], op["operation_id"]


def test_the_connection_form_matches_the_connection_type() -> None:
    [kind] = load("contracts/connection_types.yaml")["connection_types"]
    assert set(kind["config_schema"]["properties"]) == set(CONFIG_FIELDS)
    assert set(kind["secret_schema"]["properties"]) == set(SECRET_FIELDS) == {"api_key"}
    form = load("ui/pages/connection.yaml")["components"][0]
    assert {f["path"] for f in form["fields"]} == set(CONFIG_FIELDS) | set(SECRET_FIELDS)
    assert form["data"]["test_action"] == catalog.TEST_CONNECTION


def test_coverage_names_every_endpoint() -> None:
    cov = json.loads((BUNDLE / "tests/reference/coverage.json").read_text())
    assert len(cov["endpoints"]) == 600
    assert cov["source"]["sha256"] == (
        "8b8892c09f133a9ae2579ff0c93bb99e6950268960365a109a954ec4c72c47d4"
    )
    for row in cov["endpoints"]:
        assert row["status"] == "step" and row["release"] == "0.1.0" and row["reason"], row
    ops = {o["operation_id"] for o in load("contracts/operation_manifest.yaml")["operations"]}
    assert {r["operation_id"] for r in cov["endpoints"]} <= ops


def test_the_facts_are_pinned_to_the_documentation_they_came_from() -> None:
    facts = json.loads((BUNDLE / "tests/reference/b1_api.json").read_text())
    registry = json.loads((BUNDLE / "runtime/registry.json").read_text())
    assert facts["source"] == registry["source"]
    assert facts["source"]["url"] == "https://site.pro/My-Accounting/doc/api/api_data.json"


def test_the_icon_is_a_square_png_described_in_branding() -> None:
    data = (BUNDLE / "icon.png").read_bytes()
    width, height = struct.unpack(">II", data[16:24])
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and width == height and 32 <= width <= 512
    assert hashlib.sha256(data).hexdigest() in (BUNDLE / "BRANDING.md").read_text()


def test_ui_pages_hold_no_markdown_tables() -> None:
    for path in (BUNDLE / "ui" / "pages").glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"^\s*\|.*\|\s*$", text, re.M), path
        assert "|+" not in text, path


def test_customer_texts_list_nothing_unverified() -> None:
    texts = [BUNDLE / "README.md", BUNDLE / "CHANGELOG.md", BUNDLE / "extension.yaml"]
    texts += sorted((BUNDLE / "ui").rglob("*.yaml"))
    for path in texts:
        text = path.read_text(encoding="utf-8")
        for phrase in ("Not verified", "not verified", "Limits", "Advanced ·"):
            assert phrase not in text, (path.name, phrase)


def test_the_runtime_calls_no_address_but_site_pro() -> None:
    for path in (BUNDLE / "runtime").glob("*.py"):
        for host in re.findall(r"https?://([a-z0-9.-]+)", path.read_text(encoding="utf-8")):
            assert host == "site.pro", (path, host)


def test_versions_agree() -> None:
    version = load("extension.yaml")["version"]
    assert re.search(rf"^## {re.escape(version)} — ", (BUNDLE / "CHANGELOG.md").read_text(), re.M)


def test_health() -> None:
    import health

    report = health.check_health()
    assert report["ok"] is True and report["declared_operations"] == 610


# -- one object or several: what a refusal can prove ----------------------------------------

WRITES = [r for r in plan.plan() if r["kind"] in plan.WRITE_KINDS]


def test_every_write_says_how_many_objects_it_changes() -> None:
    assert len(WRITES) == 346
    registry = generic.registry()
    for row in WRITES:
        entry = registry[row["operation_id"]]
        assert row["objects"] in {"one", "several", "by_ids"}, row["path"]
        assert entry["objects"] == row["objects"]
        assert entry["single_object"] is (row["objects"] == "one"), row["path"]
    for row in plan.plan():
        if row["kind"] not in plan.WRITE_KINDS:
            assert row["objects"] == "", row["path"]


def test_one_object_only_when_the_inputs_can_name_nothing_more() -> None:
    lists = {"decimal_list", "json", "object", "object_list"}
    registry = generic.registry()
    for row in WRITES:
        entry = registry[row["operation_id"]]
        nested = [n for n in entry["params"] if n["kind"] in lists]
        if row["objects"] == "one" and row["kind"] != "delete":
            assert not nested, row["path"]
            assert row["path"] not in plan.SEVERAL_OBJECTS, row["path"]
        if row["kind"] == "delete":
            many = any(n["kind"] in {"decimal_list", "object_list"} for n in entry["params"])
            assert row["objects"] == ("by_ids" if many else "one"), row["path"]
            assert entry["max_ids"] == (50 if many else 1), row["path"]
    for path in plan.SEVERAL_OBJECTS:
        assert next(r for r in WRITES if r["path"] == path)["objects"] == "several", path
    counts = collections.Counter(r["objects"] for r in WRITES)
    assert counts == {"one": 234, "several": 15, "by_ids": 97}, counts


def test_dangerous_steps_are_strict_and_say_what_cannot_be_undone() -> None:
    registry = generic.registry()
    ops = {o["operation_id"]: o for o in load("contracts/operation_manifest.yaml")["operations"]}
    deletes = [r for r in plan.plan() if r["danger"] == "delete"]
    irreversible = [r for r in plan.plan() if r["danger"] == "irreversible"]
    assert len(deletes) == 117 and len(irreversible) == 23
    for row in deletes:
        op = ops[row["operation_id"]]
        assert op["display_name"].startswith("Delete "), row["path"]
        assert op["description"].endswith("Deletion cannot be undone."), row["path"]
        assert registry[row["operation_id"]]["strict"] is True
    for row in irreversible:
        op = ops[row["operation_id"]]
        assert "the step cannot undo it" in op["description"], row["path"]
        assert registry[row["operation_id"]]["strict"] is True
    for row in plan.plan():
        if not row["danger"] and row["kind"] in plan.WRITE_KINDS:
            assert registry[row["operation_id"]]["strict"] is False, row["path"]
    assert set(plan.IRREVERSIBLE_ACTIONS) <= {r["path"] for r in irreversible}
    salary = {r["path"] for r in irreversible if r["path"].startswith("salary/")}
    assert len(salary) == 14


def test_the_picker_lists_everyday_steps_first_and_dangerous_ones_last_in_each_group() -> None:
    ops = load("contracts/operation_manifest.yaml")["operations"]
    assert [o["operation_id"] for o in ops[: len(composites.COMPOSITES)]] == [
        s["operation_id"] for s in build_contracts.composite_specs.steps()
    ]
    rows = {r["operation_id"]: r for r in plan.plan()}
    groups = {plan.operation_id(e["path"]): e["group"] for e in plan.endpoints()}
    order = [g for g, _ in build_contracts.GROUPS]
    keys = [
        (
            order.index(groups[op["operation_id"]]),
            build_contracts.DANGER_ORDER[rows[op["operation_id"]]["danger"]],
        )
        for op in ops[len(composites.COMPOSITES) :]
    ]
    assert keys == sorted(keys)


def test_the_deletion_inputs_take_ids_only() -> None:
    forms = {f["operation_id"]: f for f in load("contracts/operation_manifest.yaml")["operations"]}
    for row in plan.plan():
        if row["kind"] != "delete":
            continue
        for item in forms[row["operation_id"]]["inputs"][1:]:
            schema = item["schema"]
            if schema.get("type") == "array":
                assert schema["minItems"] == 1 and schema["maxItems"] == 50, row["path"]
                inner = schema["items"]
                if inner.get("type") == "object":
                    assert all(
                        p == {"type": "integer", "minimum": 1} for p in inner["properties"].values()
                    ), row["path"]
                else:
                    assert inner == {"type": "integer", "minimum": 1}, row["path"]
            elif schema.get("type") == "integer":
                assert schema["minimum"] == 1, row["path"]
