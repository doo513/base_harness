import json

import pytest

from harness.config import harness_config_from_mapping
from harness.core.retrieval import RetrievalRequest
from harness.core.state import Claim, HarnessState
from harness.core.storage import IntegrityError
from harness.project_memory import ProjectMemoryError, ProjectMemoryStore


def _artifact_ref(ch="a"):
    return "artifact://" + (ch * 64) + "_evidence.json"


def _state_with_memory_candidate():
    state = HarnessState(step=7)
    ref = _artifact_ref()
    state.artifacts.append(ref)
    state.evidence_refs.append(ref)
    state.propose(Claim(
        "memory_candidate.auth-layout",
        {"kind": "project", "content": "Authentication code lives under src/auth.", "tags": ["auth", "layout"]},
        evidence_refs=[ref],
    ))
    return state


def test_project_memory_publishes_untrusted_candidate_and_retrieves_next_snapshot(tmp_path):
    workspace = tmp_path / "workspace"
    memory_root = tmp_path / "memory"
    workspace.mkdir()
    store = ProjectMemoryStore(memory_root, project_id="demo", workspace_root=workspace)
    state = _state_with_memory_candidate()

    frozen_before = store.snapshot_gateway()
    before_descriptor = frozen_before.descriptor()
    report = store.publish_from_state(state, source_run_id="run-1")
    assert len(report["published"]) == 1
    assert report["rejected"] == []
    assert frozen_before.descriptor() == before_descriptor

    gateway = store.snapshot_gateway()
    assert gateway.descriptor()["provider_id"] == "project_memory"
    assert gateway.descriptor()["index_hash"] != before_descriptor["index_hash"]
    request = RetrievalRequest(
        request_id="request",
        query="Authentication",
        normalized_query="Authentication",
        scope="project",
        top_k=5,
        requested_step=0,
        strategy_generation=0,
    )
    candidates = gateway.search(request)
    assert len(candidates) == 1
    assert candidates[0].content == "Authentication code lives under src/auth."
    assert candidates[0].metadata["trust"] == "untrusted_project_memory"


def test_project_memory_rejects_unregistered_or_ungrounded_candidates(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    store = ProjectMemoryStore(tmp_path / "memory", project_id="demo", workspace_root=workspace)
    state = HarnessState(step=1)
    state.propose(Claim(
        "memory_candidate.bad",
        {"kind": "project", "content": "trust me", "tags": []},
        evidence_refs=[],
    ))
    report = store.publish_from_state(state, source_run_id="run-1")
    assert report["published"] == []
    assert report["rejected"][0]["key"] == "memory_candidate.bad"


def test_project_memory_integrity_and_workspace_separation_fail_closed(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(ProjectMemoryError):
        ProjectMemoryStore(workspace / ".memory", project_id="demo", workspace_root=workspace)

    store = ProjectMemoryStore(tmp_path / "memory", project_id="demo", workspace_root=workspace)
    report = store.publish_from_state(_state_with_memory_candidate(), source_run_id="run-1")
    record_id = report["published"][0]
    path = store.items_dir / f"{record_id}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["body"]["content"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(IntegrityError):
        store.load_records()


def test_memory_config_is_explicit_and_disabled_by_default(tmp_path):
    default = harness_config_from_mapping({})
    assert default.memory.enabled is False
    configured = harness_config_from_mapping({
        "memory": {"enabled": True, "root": str(tmp_path / "memory"), "project_id": "demo"}
    })
    assert configured.memory.enabled is True
    assert configured.memory.project_id == "demo"
