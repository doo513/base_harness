import json
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else "ready"

for line in sys.stdin:
    request = json.loads(line)
    if mode == "crash":
        raise SystemExit(17)
    if mode == "malformed":
        print("{not-json", flush=True)
        continue
    request_type = request["type"]
    if request_type == "hello":
        payload = {"protocolVersion": 1}
    elif request_type == "run.open":
        payload = {
            "state": "open",
            "goal": request["payload"]["goalContract"]["goal"],
            "runId": request["runId"],
            "scopeId": request["scopeId"],
            "rootScopeId": request["scopeId"],
            "evidenceRefs": [],
            "candidateRefs": [],
            "readyRef": None,
            "maxSameFailureRepairs": 2,
        }
    elif request_type == "action.observe":
        payload = {
            "state": "observing",
            "runId": request["runId"],
            "scopeId": request["scopeId"],
            "rootScopeId": "root",
            "evidenceRefs": [],
            "candidateRefs": [],
            "readyRef": None,
            "maxSameFailureRepairs": 2,
        }
    elif request_type == "verify.request":
        payload = {
            "state": "ready",
            "outcome": "ready",
            "runId": request["runId"],
            "scopeId": request["scopeId"],
            "rootScopeId": "root",
            "evidenceRefs": [],
            "candidateRefs": [],
            "readyRef": {
                "artifactType": "ready",
                "sha256": "fixture",
                "path": "fixture",
                "trust": "verifier_attested",
            },
            "maxSameFailureRepairs": 2,
        }
    else:
        payload = {
            "state": "closed",
            "runId": request["runId"],
            "scopeId": request["scopeId"],
            "rootScopeId": "root",
            "evidenceRefs": [],
            "candidateRefs": [],
            "readyRef": None,
            "maxSameFailureRepairs": 2,
        }
    print(
        json.dumps(
            {
                "version": 2 if mode == "version-mismatch" else 1,
                "id": request["id"],
                "runId": request["runId"],
                "scopeId": request["scopeId"],
                "type": "response",
                "payload": payload,
            }
        ),
        flush=True,
    )
