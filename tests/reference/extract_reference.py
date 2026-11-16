#!/usr/bin/env python3
"""Extract the facts this extension needs from Site.pro Accounting's apidoc data.

    python3 tests/reference/extract_reference.py <api_data.json> <api_project.json>

writes tests/reference/b1_api.json: for each of the documented endpoints its path,
group, action, parameters (name, type, required, allowed values, size, scale), the
extra headers of file uploads, the fields of its answer (with their scale) and
whether it answers with a file. The vendor's documentation itself is not copied;
descriptions are kept short, as help texts.

Scale: the documentation writes some amounts as integers "multiplied by N"
(×100, ×1000, ×10000, ×1000000). That N is recorded per field, so the steps take a
decimal and send the integer, and read a scaled answer field back as a decimal.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
OUT = HERE / "b1_api.json"
COMMON_HEADERS = {"Content-Type", "Content-Length", "B1-Api-Key"}
_SCALE_RE = re.compile(r"multiplied by\s+(\d+)", re.IGNORECASE)
_SIZE_RE = re.compile(r"^(\d*)\.\.(\d+)$")


def text(value: str | None, limit: int) -> str:
    """Plain, single-line text of an HTML description, bounded."""
    plain = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    plain = " ".join(plain.split())
    return plain if len(plain) <= limit else plain[: limit - 1].rstrip() + "…"


def scale_of(description: str) -> int | None:
    match = _SCALE_RE.search(description)
    return int(match.group(1)) if match else None


def field(entry: dict[str, Any], *, answer: bool) -> dict[str, Any]:
    description = text(entry.get("description"), 400)
    out: dict[str, Any] = {
        "field": entry["field"],
        "type": str(entry.get("type") or ""),
        "description": description,
    }
    scale = scale_of(description)
    if scale:
        out["scale"] = scale
    if not answer:
        out["required"] = not entry.get("optional", False)
        if entry.get("allowedValues"):
            out["allowed"] = [str(v).strip('"') for v in entry["allowedValues"]]
        size = _SIZE_RE.match(str(entry.get("size") or ""))
        if size:
            out["max_length"] = int(size.group(2))
    return out


def endpoint(entry: dict[str, Any]) -> dict[str, Any]:
    path = entry["url"].strip("/")
    params = [
        field(f, answer=False)
        for group in (entry.get("parameter") or {}).get("fields", {}).values()
        for f in group
    ]
    answer = [
        field(f, answer=True)
        for group in (entry.get("success") or {}).get("fields", {}).values()
        for f in group
    ]
    headers = [
        {
            "field": f["field"],
            "required": not f.get("optional", False),
            "allowed": [str(v).strip('"') for v in f.get("allowedValues") or []],
            "description": text(f.get("description"), 300),
        }
        for group in (entry.get("header") or {}).get("fields", {}).values()
        for f in group
        if f["field"] not in COMMON_HEADERS
    ]
    names = {p["field"] for p in params}
    return {
        "path": path,
        "group": entry["group"],
        "action": path.rsplit("/", 1)[-1],
        "title": entry.get("title") or "",
        "description": text(entry.get("description"), 600),
        "params": params,
        "headers": headers,
        "answer": answer,
        "answers_file": any(a["type"] == "File" for a in answer),
        "cursor": "cursor" in names,
        "rows": "rows" in names,
    }


def main(data_path: str, project_path: str) -> None:
    raw = Path(data_path).read_bytes()
    project = json.loads(Path(project_path).read_text(encoding="utf-8"))
    data = json.loads(raw)
    endpoints = sorted((endpoint(e) for e in data), key=lambda e: e["path"])
    paths = [e["path"] for e in endpoints]
    if len(paths) != len(set(paths)):
        raise SystemExit("duplicate paths in the documentation")
    payload = {
        "source": {
            "url": "https://site.pro/My-Accounting/doc/api/api_data.json",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "api_name": project.get("name"),
            "api_version": project.get("version"),
            "generated": (project.get("generator") or {}).get("time"),
        },
        "endpoints": endpoints,
    }
    OUT.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
