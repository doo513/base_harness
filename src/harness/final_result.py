from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _safe_artifact(workspace: Path, artifact_target: str | None) -> dict[str, Any] | None:
    if not artifact_target:
        return None
    relative = Path(artifact_target)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    target = (workspace / relative).resolve()
    try:
        target.relative_to(workspace)
    except ValueError:
        return None
    if not target.exists() or not target.is_file():
        return {
            "path": relative.as_posix(),
            "exists": False,
        }
    try:
        raw = target.read_bytes()
    except OSError:
        return {
            "path": relative.as_posix(),
            "exists": True,
            "readable": False,
        }
    return {
        "path": relative.as_posix(),
        "absolute_path": str(target),
        "exists": True,
        "readable": True,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def build_final_result(*, state, workspace: str | Path, artifact_target: str | None = None) -> dict[str, Any]:
    root = Path(workspace).expanduser().resolve()
    facts = []
    for key, claim in sorted(state.facts.items()):
        dumped = claim.dump() if hasattr(claim, "dump") else {"key": key, "value": str(claim)}
        facts.append(dumped)

    successful_observations = [item for item in state.observations if bool(getattr(item, "ok", False))]
    workspace_evidence = [
        item for item in successful_observations
        if getattr(item, "source", "") in {"file.read", "directory.list", "file.search"}
    ]
    evidence_refs = list(dict.fromkeys(str(ref) for ref in state.evidence_refs))
    failures = list(state.failures[-5:])

    return {
        "schema_version": "final-result-v1",
        "completed": bool(state.completed),
        "steps": int(state.step),
        "workspace": str(root),
        "artifact": _safe_artifact(root, artifact_target),
        "evidence": {
            "registered_refs": len(evidence_refs),
            "workspace_observations": len(workspace_evidence),
            "successful_tool_observations": len(successful_observations),
            "refs": evidence_refs,
        },
        "verified_facts": {
            "count": len(facts),
            "items": facts,
        },
        "last_failures": failures,
    }


def persist_final_result(
    run_dir: str | Path,
    *,
    state,
    workspace: str | Path,
    artifact_target: str | None = None,
) -> Path:
    path = Path(run_dir).expanduser().resolve() / "final_result.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_final_result(state=state, workspace=workspace, artifact_target=artifact_target)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path
