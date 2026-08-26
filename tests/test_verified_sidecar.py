from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from harness.verified_sidecar import PROTOCOL_VERSION, VerifiedSidecar, serve


def _message(
    request_type: str,
    payload: dict[str, object],
    *,
    run_id: str = "run-1",
    scope_id: str = "root",
) -> dict[str, object]:
    return {
        "version": PROTOCOL_VERSION,
        "id": request_type,
        "runId": run_id,
        "scopeId": scope_id,
        "type": request_type,
        "payload": payload,
    }


def _open(sidecar: VerifiedSidecar, workspace: Path, run_id: str = "run-1") -> None:
    sidecar.handle(
        _message(
            "run.open",
            {
                "workspace": str(workspace),
                "goalContract": {
                    "goal": "Verify a local change",
                    "acceptance": ["The independent check passes."],
                    "constraints": [],
                },
            },
            run_id=run_id,
        )
    )


def test_ready_requires_action_and_independent_check(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "base-harness.jsonc").write_text(
        json.dumps(
            {
                "verification": {
                    "checks": [
                        {
                            "id": "independent",
                            "command": [sys.executable, "-c", "print('ok')"],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    sidecar = VerifiedSidecar(tmp_path / "state")
    _open(sidecar, workspace)

    missing = sidecar.handle(_message("verify.request", {"reason": "manual"}))
    assert missing["outcome"] == "repair"
    assert missing["failedCriterion"] == "missing_action_evidence"

    sidecar.handle(
        _message(
            "action.observe",
            {
                "tool": "write",
                "status": "completed",
                "output": {"token": "must-not-be-trusted"},
            },
        )
    )
    result = sidecar.handle(_message("verify.request", {"reason": "manual"}))

    assert result["outcome"] == "ready"
    assert result["readyRef"]["trust"] == "verifier_attested"
    assert result["evidenceRefs"][0]["trust"] == "verifier_observed"
    assert not str(result["readyRef"]["path"]).startswith(str(workspace))


def test_same_failure_blocks_after_two_repairs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "base-harness.jsonc").write_text(
        json.dumps(
            {
                "verification": {
                    "maxSameFailureRepairs": 2,
                    "checks": [
                        {
                            "id": "always-fails",
                            "command": [sys.executable, "-c", "raise SystemExit(7)"],
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    sidecar = VerifiedSidecar(tmp_path / "state")
    _open(sidecar, workspace)
    sidecar.handle(_message("action.observe", {"tool": "write", "status": "completed"}))

    outcomes = [
        sidecar.handle(_message("verify.request", {"reason": "automatic"}))["outcome"]
        for _ in range(3)
    ]
    assert outcomes == ["repair", "repair", "blocked"]


def test_protocol_version_mismatch_is_fail_closed(tmp_path: Path) -> None:
    request = _message("hello", {})
    request["version"] = 999
    output = io.StringIO()

    assert serve(io.StringIO(json.dumps(request) + "\n"), output, VerifiedSidecar(tmp_path)) == 0
    response = json.loads(output.getvalue())
    assert response["type"] == "failure"
    assert response["payload"]["outcome"] == "failure"
    assert response["payload"]["failureKind"] == "harness_protocol_version_mismatch"


def test_provider_failure_prevents_ready_until_a_successful_repair(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "base-harness.jsonc").write_text(
        json.dumps(
            {
                "verification": {
                    "checks": [
                        {
                            "id": "passes",
                            "command": [sys.executable, "-c", "print('ok')"],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    sidecar = VerifiedSidecar(tmp_path / "state")
    _open(sidecar, workspace)
    sidecar.handle(
        _message(
            "action.observe",
            {
                "tool": "model",
                "status": "error",
                "error": "provider authentication rejected the API key",
                "metadata": {"failureKind": "model_provider_error"},
            },
        )
    )

    failed = sidecar.handle(_message("verify.request", {"reason": "automatic"}))
    assert failed["outcome"] == "repair"
    assert failed["failureKind"] == "model_provider_error"
    assert failed["readyRef"] is None

    sidecar.handle(
        _message("action.observe", {"tool": "model", "status": "completed"})
    )
    repaired = sidecar.handle(_message("verify.request", {"reason": "automatic"}))
    assert repaired["outcome"] == "ready"
