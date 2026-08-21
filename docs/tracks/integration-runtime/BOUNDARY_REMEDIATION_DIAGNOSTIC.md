# Boundary Remediation Diagnostic

- apply: failure
- install: skipped
- focused: skipped
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
 src/harness/tui_conversation.py             | 241 ++++++++++++++++++++++++++--
 tests/test_hardening.py                     |   2 +-
 tests/test_integration_mcp_plugin.py        |  33 ++++
 tests/test_integration_model_gateway.py     |  25 +++
 tests/test_integration_tui.py               |  16 ++
 tests/test_task_intake_artifact_contract.py |   6 +
 tests/test_tui_conversation_v2.py           |  45 ++++++
 16 files changed, 706 insertions(+), 46 deletions(-)
```

## Last failing step log
```text
boundary deep remediation patches applied
```
