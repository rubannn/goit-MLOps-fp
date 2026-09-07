"""Pushes structured Model Registry audit events straight to Loki's push API (C5).

These scripts (train_and_push.py, promote_model.py, rollback_model.py) run
locally against port-forwarded cluster services, not as in-cluster pods, so
they have no stdout that Promtail could scrape — pushing directly to Loki is
the simplest way to get transition/archival events into the same log store
as everything else, queryable next to the inference service's logs.
"""

import json
import os
import time

import requests

LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100")


def audit_event(action: str, **fields) -> None:
    payload = {"event": "model_registry_audit", "action": action, **fields}
    body = {
        "streams": [
            {
                "stream": {"job": "model-registry-audit", "action": action},
                "values": [[str(time.time_ns()), json.dumps(payload)]],
            }
        ]
    }
    try:
        resp = requests.post(f"{LOKI_URL}/loki/api/v1/push", json=body, timeout=5)
        resp.raise_for_status()
    except requests.RequestException as e:
        # audit logging must never block the actual registry operation —
        # print so it's still visible in the script's own console output
        print(f"[audit_log] failed to push to Loki ({LOKI_URL}): {e}")
