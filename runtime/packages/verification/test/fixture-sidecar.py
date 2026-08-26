from __future__ import annotations

import json
import sys


mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
status = {
    "state": "open",
    "goal": "fixture",
    "rootScopeId": "root",
    "contractStatus": "accepted",
    "criterionResults": [],
    "claimResults": [],
    "evidenceFamilies": [],
    "evidenceRefs": [],
    "candidateRefs": [],
    "readyRef": None,
    "maxSameFailureRepairs": 2,
}

for line in sys.stdin:
    request = json.loads(line)
    if mode == "crash":
        raise SystemExit(7)
    if mode == "malformed":
        print("{not-json", flush=True)
        continue
    version = 999 if mode == "version-mismatch" else 2
    request_type = request["type"]
    payload = dict(status)
    if request_type == "hello":
        payload = {"protocolVersion": version}
    elif request_type == "run.open":
        status.update(
            {
                "runId": request["runId"],
                "scopeId": request["scopeId"],
                "rootScopeId": request["scopeId"],
                "goalContract": request["payload"].get("goalContract"),
            }
        )
        payload = dict(status)
    elif request_type == "action.close":
        status["candidateRefs"] = [
            {
                "artifactType": "action_observation",
                "sha256": "a" * 64,
                "path": "/fixture/candidate",
                "trust": "untrusted_execution_observation",
            }
        ]
        payload = dict(status)
    elif request_type == "verify.request":
        ready = {
            "artifactType": "ready_attestation",
            "sha256": "b" * 64,
            "path": "/fixture/ready",
            "trust": "verifier_attested",
        }
        status.update({"state": "ready", "outcome": "ready", "readyRef": ready})
        payload = dict(status)
    elif request_type == "run.close":
        status["state"] = "closed"
        payload = dict(status)
    print(
        json.dumps(
            {
                "version": version,
                "id": request["id"],
                "runId": request["runId"],
                "scopeId": request["scopeId"],
                "type": "response",
                "payload": payload,
            }
        ),
        flush=True,
    )
