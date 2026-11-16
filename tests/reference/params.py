"""Documented parameters as a tree, and the JSON schema of a step input built from it.

Shared by the contract builder (forms, manifests) and the runtime registry, so the
form a user fills in and the checks the runtime makes come from the same facts.
"""

from __future__ import annotations

from typing import Any

#: Documented type -> the kind the runtime checks.
TYPES = {
    "String": "text",
    "Date": "text",
    "date": "text",
    "Array/String": "text",
    "Number": "decimal",
    "Float": "decimal",
    "float": "decimal",
    "Numeric": "decimal",
    "Integer": "integer",
    "id": "integer",
    "Boolean": "boolean",
    "Number[]": "decimal_list",
    "Number[][]": "json",
    "Array": "json",
    "Object": "object",
    "Object[]": "object_list",
}
LIST_PARAMS = frozenset({"rows", "page", "cursor", "sidx", "sord", "filters"})


def tree(
    params: list[dict[str, Any]], *, skip: frozenset[str] = frozenset()
) -> list[dict[str, Any]]:
    """Nested parameter nodes from the documentation's dotted names."""
    roots: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    def node_for(parts: list[str], source: dict[str, Any] | None) -> dict[str, Any]:
        level = roots
        node: dict[str, Any] = {}
        for i, part in enumerate(parts):
            if part not in level:
                level[part] = {"name": part, "kind": "object", "required": False, "children": {}}
                if level is roots:
                    order.append(part)
            node = level[part]
            if i < len(parts) - 1:
                if node["kind"] not in {"object", "object_list"}:
                    node["kind"] = "object"
                level = node["children"]
        if source is not None:
            node["kind"] = TYPES.get(source["type"], "text")
            if source.get("scale") and node["kind"] == "text":
                # A scaled amount typed String (shop/orders/add payment.sum, .tax): the step
                # takes a decimal and sends the whole number as text, as the type says.
                node["kind"] = "decimal"
                node["as_text"] = True
            node["required"] = bool(source.get("required"))
            for key in ("scale", "allowed", "max_length"):
                if source.get(key):
                    node[key] = source[key]
            node["description"] = source.get("description", "")
        return node

    for param in params:
        name = param["field"]
        if name.split(".")[0] in skip:
            continue
        node_for(name.split("."), param)

    def finish(node: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in node.items() if k != "children"}
        children = [finish(c) for c in node.get("children", {}).values()]
        if children:
            out["children"] = children
        elif out["kind"] in {"object", "object_list"} and "children" in node:
            out["children"] = []
        return out

    return [finish(roots[name]) for name in order]


def schema(node: dict[str, Any]) -> dict[str, Any]:
    """The JSON schema of one input or record field."""
    kind = node["kind"]
    description = node.get("description") or ""
    if node.get("scale"):
        description = (
            f"{description} Give the plain amount; the step sends it multiplied by {node['scale']}."
        ).strip()
    out: dict[str, Any]
    if kind == "text":
        out = {"type": "string"}
        if node.get("max_length"):
            out["maxLength"] = node["max_length"]
        if node.get("allowed"):
            out["enum"] = list(node["allowed"])
    elif kind == "decimal":
        out = {"type": ["number", "string"]}
    elif kind == "integer":
        out = {"type": "integer"}
    elif kind == "boolean":
        out = {"type": "boolean"}
    elif kind == "decimal_list":
        out = {"type": "array", "items": {"type": ["number", "string"]}}
    elif kind == "json":
        out = {"type": "array"}
    else:
        children = node.get("children") or []
        properties = {c["name"]: schema(c) for c in children}
        record: dict[str, Any] = {"type": "object"}
        if properties:
            record.update(
                additionalProperties=False,
                required=[c["name"] for c in children if c.get("required")],
                properties=properties,
            )
        out = {"type": "array", "items": record} if kind == "object_list" else record
    if description:
        out["description"] = description[:400]
    return out


def value_type(node: dict[str, Any]) -> str:
    return {
        "text": "text",
        "decimal": "text",
        "integer": "integer",
        "boolean": "boolean",
        "decimal_list": "array",
        "json": "array",
        "object": "object",
        "object_list": "array",
    }[node["kind"]]


__all__ = ["LIST_PARAMS", "TYPES", "schema", "tree", "value_type"]
