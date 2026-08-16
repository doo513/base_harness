from pathlib import Path

from harness.core.controller import DirectController
from harness.core.runtime import HarnessRuntime
from harness.profiles.demo import DemoProfile


def _runtime(tmp_path: Path, *, resume: bool = False) -> HarnessRuntime:
    return HarnessRuntime(
        goal=DemoProfile().default_goal(),
        profile=DemoProfile(),
        controller=DirectController(),
        run_dir=tmp_path / "run",
        workspace=tmp_path / "workspace",
        resume=resume,
    )


def test_build_provenance_is_persisted_and_semantically_fingerprinted(tmp_path):
    (tmp_path / "workspace").mkdir()
    runtime = _runtime(tmp_path)

    audit = runtime.manifest_body.get("build_provenance")
    assert isinstance(audit, dict)
    assert audit["semantic_hash"] == runtime.build_provenance.semantic_hash
    assert audit["dependency_lock_sha256"] == runtime.build_provenance.dependency_lock_sha256
    assert audit["git"] == runtime.build_provenance.git

    semantic = runtime.manifest_body["config"]["build_provenance"]
    assert semantic == runtime.build_provenance.semantic_descriptor()
    assert "git" not in semantic
    assert "source_semantic_hash" in semantic


def test_resume_reuses_same_build_semantics(tmp_path):
    (tmp_path / "workspace").mkdir()
    first = _runtime(tmp_path)
    first.run()

    resumed = _runtime(tmp_path, resume=True)
    assert resumed.build_provenance.semantic_hash == first.build_provenance.semantic_hash
    assert resumed.manifest_body["config"]["build_provenance"] == resumed.build_provenance.semantic_descriptor()
