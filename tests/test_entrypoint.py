"""main.py and health.py as the host runs them: a subprocess, JSON in and out."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from support import API_KEY, BUNDLE, payload


def invoke(request: Any) -> tuple[int, dict[str, Any]]:
    proc = subprocess.run(
        [sys.executable, "main.py"],
        cwd=BUNDLE,
        input=json.dumps(request) if not isinstance(request, bytes) else request.decode(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return proc.returncode, json.loads(proc.stdout)


def test_a_test_mode_write_answers_without_network() -> None:
    request = payload("clients_create", {"name": "UAB", "locationId": 1}, test_mode=True)
    code, response = invoke(request)
    assert code == 0, response
    assert response["definitely_no_external_effect"] is True
    assert API_KEY not in json.dumps(response)


def test_an_unknown_operation_is_refused() -> None:
    code, response = invoke(payload("drop_everything"))
    assert code == 2
    assert response["error_code"] == "unsupported_operation"


def test_a_request_that_is_not_json_is_refused() -> None:
    code, response = invoke(b"{not json")
    assert code == 2
    assert response["error_code"] == "invalid_payload"


def test_health_answers_without_network() -> None:
    proc = subprocess.run(
        [sys.executable, "health.py"], cwd=BUNDLE, capture_output=True, text=True, check=True
    )
    report = json.loads(proc.stdout)
    assert report["ok"] is True
    assert report["extension_id"] == "flowsteward.b1"
