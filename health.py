"""Health command for the B1 extension (no network)."""

from __future__ import annotations

import json


def check_health() -> dict[str, object]:
    from runtime.catalog import OPERATION_IDS, WRITE_OPERATION_IDS
    from runtime.connection import BASE_URL
    from runtime.generic import REGISTRY_FILE

    source = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))["source"]
    return {
        "extension_id": "flowsteward.b1",
        "ok": True,
        "status": "healthy",
        "api": BASE_URL,
        "documentation_sha256": source["sha256"],
        "documentation_version": source["api_version"],
        "declared_operations": len(OPERATION_IDS),
        "effect_operations": len(WRITE_OPERATION_IDS),
    }


if __name__ == "__main__":
    print(json.dumps(check_health(), separators=(",", ":"), sort_keys=True))
