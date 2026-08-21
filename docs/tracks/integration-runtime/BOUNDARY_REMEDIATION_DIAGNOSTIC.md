# Boundary Remediation Diagnostic

- apply: success
- install: success
- focused: failure
- full: skipped

## Proposed diff stat before reset
```text
 .github/workflows/research-ci.yml           |  20 ++++
 src/harness/core/controller.py              | 153 ++++++++++++++++++++++++-
 src/harness/core/failures.py                |  12 ++
 src/harness/core/runtime_execution.py       |  61 +++++++++-
 src/harness/mcp_gateway.py                  |  19 ++++
 src/harness/model_gateway.py                |  61 +++++++++-
 src/harness/task_intake.py                  |  18 +--
 src/harness/tui.py                          |  29 +++--
 src/harness/tui_conversation.py             | 170 ++++++++++++++++++++++++++--
 tests/test_integration_mcp_plugin.py        |  33 ++++++
 tests/test_integration_model_gateway.py     |  25 ++++
 tests/test_integration_tui.py               |  16 +++
 tests/test_task_intake_artifact_contract.py |   6 +
 tests/test_tui_conversation_v2.py           |  45 ++++++++
 14 files changed, 624 insertions(+), 44 deletions(-)
```

## Last failing step log
```text
...............................F.....                                    [100%]
=================================== FAILURES ===================================
_________ test_mcp_stdio_drains_legal_stderr_logging_without_deadlock __________

    def test_mcp_stdio_drains_legal_stderr_logging_without_deadlock():
        client = MCPStdioClient(
            command=(sys.executable, "-u", "-c", _stderr_heavy_server_script()),
            request_timeout_seconds=2.0,
            probe_timeout_seconds=1.0,
        )
        try:
            assert client.list_tools() == []
>           assert client.stderr_tail()
E           assert ()
E            +  where () = stderr_tail()
E            +    where stderr_tail = <harness.mcp_gateway.MCPStdioClient object at 0x7f736a35ae50>.stderr_tail

tests/test_integration_mcp_plugin.py:234: AssertionError
=========================== short test summary info ============================
FAILED tests/test_integration_mcp_plugin.py::test_mcp_stdio_drains_legal_stderr_logging_without_deadlock - assert ()
 +  where () = stderr_tail()
 +    where stderr_tail = <harness.mcp_gateway.MCPStdioClient object at 0x7f736a35ae50>.stderr_tail
1 failed, 36 passed in 0.75s
```
