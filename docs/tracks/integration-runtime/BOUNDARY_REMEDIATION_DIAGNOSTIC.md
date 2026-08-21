# Boundary Remediation Diagnostic

- apply: success
- install: success
- focused: success
- full: failure

## Proposed diff stat before reset
```text
 .github/workflows/research-ci.yml           |  20 ++++
 scripts/apply_boundary_deep_remediation.py  |   2 +-
 src/harness/core/controller.py              | 153 ++++++++++++++++++++++++-
 src/harness/core/failures.py                |  12 ++
 src/harness/core/runtime_execution.py       |  61 +++++++++-
 src/harness/mcp_gateway.py                  |  25 ++++
 src/harness/model_gateway.py                |  61 +++++++++-
 src/harness/task_intake.py                  |  18 +--
 src/harness/tui.py                          |  29 +++--
 src/harness/tui_conversation.py             | 170 ++++++++++++++++++++++++++--
 tests/test_integration_mcp_plugin.py        |  33 ++++++
 tests/test_integration_model_gateway.py     |  25 ++++
 tests/test_integration_tui.py               |  16 +++
 tests/test_task_intake_artifact_contract.py |   6 +
 tests/test_tui_conversation_v2.py           |  45 ++++++++
 15 files changed, 631 insertions(+), 45 deletions(-)
```

## Last failing step log
```text
...............F........................................................ [ 21%]
..........ssss..s.....................................................ss [ 43%]
........................................................................ [ 65%]
........................................................................ [ 87%]
.........................................                                [100%]
=================================== FAILURES ===================================
______________ test_malformed_decision_becomes_failure_not_crash _______________

tmp_path = PosixPath('/tmp/pytest-of-runner/pytest-1/test_malformed_decision_become0')

    def test_malformed_decision_becomes_failure_not_crash(tmp_path):
        profile = SoftwareProfile(workspace=tmp_path, acceptance_commands=["false"])
        controller = ScriptedController([
            Decision("propose", {}),
        ])
        state = HarnessRuntime(
            goal=profile.default_goal(),
            profile=profile,
            controller=controller,
            run_dir=tmp_path / "run",
            workspace=tmp_path,
            budget=Budget(hard_max_steps=1),
        ).run()
        assert not state.completed
>       assert any(f["kind"] == "implementation_error" for f in state.failures)
E       assert False
E        +  where False = any(<generator object test_malformed_decision_becomes_failure_not_crash.<locals>.<genexpr> at 0x7f045feda0c0>)

tests/test_hardening.py:76: AssertionError
=========================== short test summary info ============================
FAILED tests/test_hardening.py::test_malformed_decision_becomes_failure_not_crash - assert False
 +  where False = any(<generator object test_malformed_decision_becomes_failure_not_crash.<locals>.<genexpr> at 0x7f045feda0c0>)
1 failed, 321 passed, 7 skipped in 28.88s
```
