"""The closed list of this extension's steps: the generated ones (runtime/registry.json)
and the everyday ones (runtime/composites.py)."""

from __future__ import annotations

from . import composites
from .generic import registry

TEST_CONNECTION = "test_connection"
_REGISTRY = registry()

GENERATED_IDS: frozenset[str] = frozenset(_REGISTRY)
COMPOSITE_IDS: frozenset[str] = frozenset(composites.COMPOSITES)
OPERATION_IDS: frozenset[str] = GENERATED_IDS | COMPOSITE_IDS
#: Kinds of generated steps that change data in Site.pro Accounting.
WRITE_KINDS = frozenset({"create", "update", "upload", "delete", "action", "action_file"})
#: Steps that change data in Site.pro Accounting.
EFFECT_OPERATION_IDS: frozenset[str] = (
    frozenset(oid for oid, spec in _REGISTRY.items() if spec["kind"] in WRITE_KINDS)
    | composites.COMPOSITE_WRITES
)
WRITE_OPERATION_IDS = EFFECT_OPERATION_IDS
#: Steps that save a workflow file: their requests keep the file's time in reserve.
FILE_OUTPUT_IDS: frozenset[str] = frozenset(
    oid for oid, spec in _REGISTRY.items() if spec["kind"] in {"file", "report_get", "action_file"}
) | {"get_report"}

__all__ = [
    "COMPOSITE_IDS",
    "EFFECT_OPERATION_IDS",
    "FILE_OUTPUT_IDS",
    "GENERATED_IDS",
    "OPERATION_IDS",
    "TEST_CONNECTION",
    "WRITE_KINDS",
    "WRITE_OPERATION_IDS",
]
