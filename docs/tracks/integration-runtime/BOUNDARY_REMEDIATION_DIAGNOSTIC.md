# Boundary Remediation Diagnostic

- apply: success
- install: success
- focused: failure
- full: skipped

## Proposed diff stat before reset
```text
 .github/workflows/research-ci.yml           |  20 +++
 scripts/apply_boundary_deep_remediation.py  |   2 +-
 src/harness/core/controller.py              | 153 +++++++++++++++++-
 src/harness/core/failures.py                |  12 ++
 src/harness/core/runtime_execution.py       |  61 ++++++-
 src/harness/mcp_gateway.py                  |  25 +++
 src/harness/model_gateway.py                |  61 ++++++-
 src/harness/task_intake.py                  |  18 +--
 src/harness/tui.py                          |  32 ++--
 src/harness/tui_conversation.py             | 242 ++++++++++++++++++++++++++--
 tests/test_hardening.py                     |   2 +-
 tests/test_integration_mcp_plugin.py        |  33 ++++
 tests/test_integration_model_gateway.py     |  25 +++
 tests/test_integration_tui.py               |  16 ++
 tests/test_task_intake_artifact_contract.py |   6 +
 tests/test_tui_conversation_v2.py           | 131 +++++++++++++++
 16 files changed, 793 insertions(+), 46 deletions(-)
```

## Last failing step log
```text
..................F..........................                            [100%]
=================================== FAILURES ===================================
__________ test_tui_v2_resume_spec_uses_verified_manifest_boundaries ___________

tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-0/test_tui_v2_resume_spec_uses_v0')

    def test_tui_v2_resume_spec_uses_verified_manifest_boundaries(tmp_path):
        workspace = tmp_path / "persisted-workspace"
        workspace.mkdir()
        run_dir = tmp_path / "persisted-run"
        run_dir.mkdir()
        RunManifestStore(run_dir / "run_manifest.json").create({
            "run_id": "abc",
            "harness_version": __version__,
            "model_revision": "model-x",
            "config": {
                "workspace": str(workspace),
                "profile": {"name": "ctf"},
                "goal": {"acceptance": ["python verify.py"]},
                "security": {
                    "strict_layout": True,
                    "strict_tool_isolation": True,
                    "network_policy": "deny",
                    "require_sealed_oracle": False,
                },
                "tools": [],
            },
        })
        state = AppState(workspace=str(tmp_path), config=str(tmp_path / "missing.toml"), mode="software")
        spec = _session_resume_spec(state, run_dir)
>       assert spec is not None
E       assert None is not None

tests/test_tui_conversation_v2.py:134: AssertionError
=========================== short test summary info ============================
FAILED tests/test_tui_conversation_v2.py::test_tui_v2_resume_spec_uses_verified_manifest_boundaries - assert None is not None
1 failed, 44 passed in 1.45s
```
