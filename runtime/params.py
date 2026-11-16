"""Step inputs checked against the documented parameters, and turned into the wire body.

Each node comes from runtime/registry.json (built from the documentation by
tests/reference/build_contracts.py): its name, kind, whether it is required, its
allowed values, its length and its scale. Unknown fields are refused, not dropped.

Scale: some amounts travel as integers "multiplied by N". The step takes the plain
decimal and sends ``value × N``; a value that does not become a whole number that
way (more decimals than N allows) is refused before anything is sent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, localcontext
from typing import Any

from . import values
from .errors import invalid

MAX_LIST_ITEMS = 1000
MAX_TEXT = 10_000


def scaled(value: Decimal, scale: int, what: str) -> int:
    """``value × scale`` as an exact whole number, or a refusal."""
    with localcontext() as ctx:
        ctx.prec = 60
        product = value * scale
        if product != product.to_integral_value():
            raise invalid(
                f"{what} has more decimals than Site.pro Accounting takes (it is sent "
                f"multiplied by {scale})"
            )
        return int(product)


def check(node: Mapping[str, Any], value: Any, what: str) -> Any:
    """One value checked against its node; the value to send."""
    kind = node["kind"]
    if kind == "text":
        text = values.text(
            value, what, max_length=int(node.get("max_length") or MAX_TEXT), multi_line=True
        )
        if text is None:
            raise invalid(f"{what} is empty")
        allowed = node.get("allowed")
        if allowed and text not in allowed:
            raise invalid(f"{what} must be one of: {', '.join(allowed)}")
        return text
    if kind == "decimal":
        number = values.number(value, what)
        scale = node.get("scale")
        if not scale:
            return number
        whole = scaled(number, int(scale), what)
        return str(whole) if node.get("as_text") else whole
    if kind == "integer":
        if isinstance(value, bool):
            raise invalid(f"{what} must be a whole number")
        if isinstance(value, Decimal) and value == value.to_integral_value():
            value = int(value)
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            value = int(value.strip())
        if not isinstance(value, int) or abs(value) > 10**15:
            raise invalid(f"{what} must be a whole number")
        allowed = node.get("allowed")
        if allowed and str(value) not in allowed:
            raise invalid(f"{what} must be one of: {', '.join(allowed)}")
        return value
    if kind == "boolean":
        if not isinstance(value, bool):
            raise invalid(f"{what} must be true or false")
        return value
    if kind == "decimal_list":
        if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
            raise invalid(f"{what} must be a list of at most {MAX_LIST_ITEMS} numbers")
        return [values.number(v, f"{what} item") for v in value]
    if kind == "json":
        if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
            raise invalid(f"{what} must be a list")
        return value
    if kind == "object":
        if not isinstance(value, Mapping):
            raise invalid(f"{what} must be an object")
        return body(node.get("children") or [], value, what, open_object=True)
    if kind == "object_list":
        if not isinstance(value, list) or len(value) > MAX_LIST_ITEMS:
            raise invalid(f"{what} must be a list of at most {MAX_LIST_ITEMS} objects")
        out = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, Mapping):
                raise invalid(f"{what} item {index} must be an object")
            out.append(
                body(node.get("children") or [], item, f"{what} item {index}", open_object=True)
            )
        return out
    raise invalid(f"{what} has a kind this extension does not know")  # pragma: no cover


def body(
    nodes: list[Mapping[str, Any]],
    given: Mapping[str, Any],
    where: str = "",
    *,
    open_object: bool = False,
) -> dict[str, Any]:
    """The wire body for ``given`` checked against ``nodes``: closed, typed, scaled.

    ``open_object`` is for a nested object the documentation names without its fields:
    it is passed on as given. A step's own inputs are never open.
    """
    by_name = {n["name"]: n for n in nodes}
    unknown = sorted(str(k) for k in given if k not in by_name)
    if unknown and open_object and not by_name:
        return dict(given)
    if unknown:
        raise invalid(f"{where or 'The step input'} has unknown fields: {', '.join(unknown[:10])}")
    out: dict[str, Any] = {}
    for node in nodes:
        name = node["name"]
        what = f"{where}.{name}" if where else name
        value = given.get(name)
        if value is None or value == "":
            if node.get("required"):
                raise invalid(f"{what} is required")
            continue
        out[name] = check(node, value, what)
    return out


_WHOLE_RE = re.compile(r"^[+-]?\d{1,40}$")


def unscale(
    record: Any, scales: Mapping[str, int], prefix: str = "", warnings: list[str] | None = None
) -> Any:
    """Answer fields documented as "multiplied by N" read back as plain decimals.

    A whole number, given as a number or as text of digits, is divided by N. Any other
    value in such a field (a fraction, other text) is returned as sent, and the field
    is named in ``warnings``: it cannot be read in the documented unit. Fields whose
    scale the documentation does not give are returned as sent.
    """
    if isinstance(record, list):
        return [unscale(item, scales, prefix, warnings) for item in record]
    if not isinstance(record, Mapping):
        return record
    out: dict[str, Any] = {}
    for key, value in record.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        scale = scales.get(path)
        if not scale or value is None:
            out[key] = unscale(value, scales, path, warnings) if not scale else value
            continue
        whole: Decimal | None = None
        if isinstance(value, int) and not isinstance(value, bool):
            whole = Decimal(value)
        elif isinstance(value, Decimal) and value == value.to_integral_value():
            whole = value
        elif isinstance(value, str) and _WHOLE_RE.fullmatch(value.strip()):
            whole = Decimal(value.strip())
        if whole is None:
            out[key] = value
            if warnings is not None:
                note = (
                    f"{key} is not a whole number, so it cannot be read as a plain amount "
                    f"(Site.pro Accounting documents it multiplied by {scale}); it is returned "
                    "as sent"
                )
                if note not in warnings:
                    warnings.append(note)
            continue
        with localcontext() as ctx:
            ctx.prec = 60
            out[key] = format(whole / scale, "f")
    return out


__all__ = ["body", "check", "scaled", "unscale"]
