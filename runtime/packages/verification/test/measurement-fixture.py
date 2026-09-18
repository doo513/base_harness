"""Controlled protocol-corruption fixture; real measurement code supplies the facts."""
import json
import os
import sys

from harness.measurement_v5 import MeasurementEngine

engine = MeasurementEngine()
for line in sys.stdin:
    envelope = json.loads(line)
    payload = engine.handle(envelope)
    if envelope["type"] == "measure":
        mode = os.environ["MEASUREMENT_FIXTURE_MODE"]
        if mode == "wrong-run":
            payload["runId"] = "another-run"
        elif mode == "wrong-subject":
            payload["subject"] = {**payload["subject"], "revision": 2}
        elif mode == "ready-field":
            payload["readyEligible"] = True
        elif mode == "wrong-environment":
            payload["environmentHash"] = "0" * 64
    response = {**envelope, "type": "response", "payload": payload}
    print(json.dumps(response), flush=True)
