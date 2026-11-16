"""Runners of the generated steps: one documented operation each.

What each step accepts and how its answer is read comes from runtime/registry.json,
built from the documentation by tests/reference/build_contracts.py.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from . import budget, errors, files, values
from .context import Context
from .errors import invalid
from .params import body, check, unscale

REGISTRY_FILE = Path(__file__).resolve().parent / "registry.json"
#: Documented filter operators (list parameters and the General page's examples).
OPERATORS = (
    "eq",
    "ne",
    "lt",
    "le",
    "gt",
    "ge",
    "bw",
    "bn",
    "in",
    "ni",
    "ew",
    "en",
    "cn",
    "nc",
    "nu",
    "nn",
)
MAX_FILTERS = 20
LIST_INPUTS = frozenset({"rows", "page", "cursor", "sidx", "sord", "filters"})


@cache
def registry() -> dict[str, dict[str, Any]]:
    data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return dict(data["operations"])


def spec(operation_id: str) -> dict[str, Any]:
    return registry()[operation_id]


# -- checking inputs ---------------------------------------------------------------------


def _list_body(entry: Mapping[str, Any], given: Mapping[str, Any]) -> dict[str, Any]:
    listing = entry["list"]
    out: dict[str, Any] = {}
    rows = given.get("rows", listing["default_rows"])
    out["rows"] = values.int_in(
        rows, "rows", default=listing["default_rows"], low=1, high=max(listing["rows"])
    )
    if out["rows"] not in listing["rows"]:
        raise invalid(f"rows must be one of: {', '.join(str(r) for r in listing['rows'])}")
    if given.get("cursor") is not None:
        if not listing["cursor"]:
            raise invalid("This list has no cursor")
        out["cursor"] = values.required_text(given["cursor"], "cursor", max_length=500)
    if given.get("page") is not None:
        if not listing["page"]:
            raise invalid("This list has no page number")
        if "cursor" in out:
            raise invalid("Give the cursor or the page, not both")
        out["page"] = values.int_in(given["page"], "page", default=1, low=1, high=10**7)
    if given.get("sidx") is not None:
        field = values.required_text(given["sidx"], "sidx", max_length=100)
        if field not in listing["fields"]:
            raise invalid(
                f"sidx must be a field of this list: {', '.join(listing['fields'][:20])} …"
            )
        out["sidx"] = field
    if given.get("sord") is not None:
        out["sord"] = values.choice(given["sord"], "sord", {"asc": "asc", "desc": "desc"})
    if given.get("filters") is not None:
        rules = values.records(given["filters"], "filters", max_items=MAX_FILTERS)
        checked = []
        for index, rule in enumerate(rules, start=1):
            what = f"filters item {index}"
            values.closed(rule, frozenset({"field", "op", "data"}), what)
            field = values.required_text(rule.get("field"), f"{what} field", max_length=100)
            if field not in listing["fields"]:
                raise invalid(f"{what} field {field} is not a field of this list")
            op = values.required_text(rule.get("op"), f"{what} op", max_length=2)
            if op not in OPERATORS:
                raise invalid(f"{what} op must be one of: {', '.join(OPERATORS)}")
            data = rule.get("data", "")
            data = "" if data is None else data
            if isinstance(data, bool) or not isinstance(data, (str, int)):
                raise invalid(f"{what} data must be text or a whole number")
            data_text = str(data)
            if len(data_text) > 500:
                raise invalid(f"{what} data is too long")
            checked.append({"field": field, "op": op, "data": data_text})
        out["filters"] = {"groupOp": "AND", "rules": checked}
    rest = {k: v for k, v in given.items() if k not in LIST_INPUTS}
    out.update(body(entry["params"], rest))
    return out


MAX_ID = 10**15


def _record_id(value: Any, what: str) -> int:
    """A positive whole ID; nothing else (no 0, no fraction, no range)."""
    if isinstance(value, Decimal) and value == value.to_integral_value():
        value = int(value)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ID:
        raise invalid(f"{what} must be a positive whole number (an ID)")
    return value


def _id_record(node: Mapping[str, Any], value: Any, what: str) -> dict[str, int]:
    children = node.get("children") or []
    if not isinstance(value, Mapping):
        raise invalid(f"{what} must be an object of IDs")
    names = frozenset(c["name"] for c in children)
    values.closed(value, names, what)
    out = {}
    for child in children:
        if value.get(child["name"]) is None:
            raise invalid(f"{what}.{child['name']} is required")
        out[child["name"]] = _record_id(value[child["name"]], f"{what}.{child['name']}")
    return out


def _id_list(items: Any, what: str, max_ids: int, one: Any) -> list[Any]:
    if not isinstance(items, list) or not items:
        raise invalid(f"{what} must be a list of at least one ID")
    if len(items) > max_ids:
        raise invalid(f"{what} may hold at most {max_ids} IDs per run")
    out = [one(item, f"{what} item {index}") for index, item in enumerate(items, start=1)]
    seen: list[Any] = []
    for item in out:
        if item in seen:
            raise invalid(f"{what} repeats {item}")
        seen.append(item)
    return out


def delete_body(entry: Mapping[str, Any], given: Mapping[str, Any]) -> tuple[dict[str, Any], list]:
    """(wire body, the IDs it deletes) of a deletion: explicit IDs only, closed, short."""
    nodes = entry["params"]
    max_ids = int(entry["max_ids"])
    values.closed(given, frozenset(n["name"] for n in nodes), "The step input")
    wire: dict[str, Any] = {}
    listed: list[Any] | None = None
    for node in nodes:
        name, kind = node["name"], node["kind"]
        value = given.get(name)
        if value is None or value == "":
            if node.get("required"):
                raise invalid(f"{name} is required")
            continue
        if kind == "decimal_list":
            wire[name] = listed = _id_list(value, name, max_ids, _record_id)
        elif kind == "object_list":
            wire[name] = listed = _id_list(
                value, name, max_ids, lambda item, what: _id_record(node, item, what)
            )
        elif kind == "object":
            wire[name] = _id_record(node, value, name)
            listed = [wire[name]]
        elif kind in {"integer", "decimal"}:
            wire[name] = _record_id(value, name)
        else:
            wire[name] = check(node, value, name)
    if listed is None:
        listed = [next(iter(wire.values()))] if len(wire) == 1 else [dict(wire)]
    return wire, listed


def request_body(operation_id: str, operation_input: Mapping[str, Any]) -> dict[str, Any]:
    """The checked wire body of a generated step (also its test-run check)."""
    entry = spec(operation_id)
    given = {k: v for k, v in operation_input.items() if k != "connection_ref"}
    if entry["kind"] == "delete":
        return delete_body(entry, given)[0]
    if entry["kind"] == "upload":
        values.closed(
            given,
            frozenset(h["input"] for h in entry["headers"]) | {"file", "content_type"},
            "The step input",
        )
        return {}
    if entry.get("list"):
        return _list_body(entry, given)
    return body(entry["params"], given)


def _upload_headers(entry: Mapping[str, Any], given: Mapping[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in entry["headers"]:
        value = given.get(header["input"])
        if value is None or value == "":
            if header["required"]:
                raise invalid(f"{header['input']} is required")
            continue
        if header["kind"] == "integer":
            number = values.int_in(value, header["input"], default=0, low=1, high=10**12)
            text = str(number)
        else:
            text = values.required_text(value, header["input"], max_length=255)
            if header.get("allowed") and text not in header["allowed"]:
                raise invalid(f"{header['input']} must be one of: {', '.join(header['allowed'])}")
            if not text.isprintable() or any(ord(c) > 0x7E for c in text):
                raise invalid(f"{header['input']} may use plain ASCII characters only")
        headers[header["field"]] = text
    return headers


# -- running ---------------------------------------------------------------------------------


def _data_out(entry: Mapping[str, Any], answer: Mapping[str, Any], warnings: list[str]) -> Any:
    return unscale(answer.get("data"), entry.get("answer_scales") or {}, "data", warnings)


def run(context: Context, operation_id: str) -> dict[str, Any]:
    entry = spec(operation_id)
    kind = entry["kind"]
    path = entry["path"]
    given = {k: v for k, v in context.operation_input.items() if k != "connection_ref"}
    transport = context.transport
    if kind == "upload":
        request_body(operation_id, given)
        headers = _upload_headers(entry, given)
        content = files.read_upload(context, files.artifact_handle(given.get("file"), "file"))
        content_type = values.text(given.get("content_type"), "content_type", max_length=100)
        answer = transport.upload(
            path,
            content,
            content_type=content_type or "application/octet-stream",
            headers=headers,
        )
        data = answer.get("data")
        record_id = data.get("id") if isinstance(data, Mapping) else answer.get("id")
        return {"id": record_id, "data": data, "message": answer.get("message"), "warnings": []}
    if kind == "delete":
        wire, sent = delete_body(entry, given)
        answer = transport.write(path, wire, single_object=len(sent) == 1, strict=True)
        return {
            "sent_ids": sent,
            "data": answer.get("data"),
            "message": answer.get("message"),
            "warnings": [],
        }
    wire = request_body(operation_id, given)
    if kind in {"file", "report_get", "action_file"}:
        if kind == "action_file":
            got = transport.write_file(
                path, wire, single_object=entry["single_object"], strict=entry["strict"]
            )
        else:
            got = transport.read_file(path, wire)
        if got.file is None:
            raise errors.no_effect(
                errors.INVALID_RESPONSE,
                f"Site.pro Accounting answered {path} without a file",
                failure_class="provider",
                retryable=False,
            )
        handle = files.save(
            context,
            got.file,
            binding_key=files.DOWNLOAD_BINDING,
            content_type=files.DOWNLOAD_CONTENT_TYPE,
            what="The file",
        )
        return {
            "file": handle,
            "file_name": got.file_name or None,
            "mime_type": got.content_type or None,
            "size_bytes": len(got.file),
            "warnings": [],
        }
    if kind == "report":
        answer = transport.read(path, wire)
        task = answer.get("taskId")
        if task is None and isinstance(answer.get("data"), Mapping):
            task = answer["data"].get("taskId")
        missing = [] if task is not None else ["Site.pro Accounting returned no task ID"]
        return {"task_id": task, "warnings": missing}
    warnings: list[str] = []
    if kind in {"create", "update", "action"}:
        answer = transport.write(
            path, wire, single_object=entry["single_object"], strict=entry["strict"]
        )
        data = _data_out(entry, answer, warnings)
        record_id = data.get("id") if isinstance(data, Mapping) else None
        return {
            "id": record_id,
            "data": data,
            "message": answer.get("message"),
            "warnings": warnings,
        }
    answer = transport.read(path, wire)
    if entry.get("list"):
        items = _data_out(entry, answer, warnings)
        items = items if isinstance(items, list) else ([] if items is None else [items])
        result = {
            "items": items,
            "count": len(items),
            "page": answer.get("page"),
            "pages": answer.get("pages"),
            "records": answer.get("records"),
            "next_cursor": answer.get("nextCursor"),
            "has_more": answer.get("hasMore"),
            "warnings": warnings,
        }
    else:
        result = {
            "data": _data_out(entry, answer, warnings),
            "message": answer.get("message"),
            "warnings": warnings,
        }
    budget.ensure_fits(result)
    return result


__all__ = ["OPERATORS", "delete_body", "registry", "request_body", "run", "spec"]
