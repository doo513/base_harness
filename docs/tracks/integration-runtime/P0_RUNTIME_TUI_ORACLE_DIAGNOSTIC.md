# P0 Runtime/TUI/Oracle Remediation Diagnostic

- restore: success
- apply: failure
- install: skipped
- focused: skipped
- full: skipped

## Proposed diff stat before reset
```text
 src/harness/cli.py          | 37 +++++++++++++++++---
 src/harness/core/oracles.py | 82 ++++++++++++++++++++++++++++++---------------
 2 files changed, 87 insertions(+), 32 deletions(-)
```

## Last log
```text
error: src/harness/tui.py: expected fragment not found: '        argv.append("--strict-layout" if self.strict_layout else "--no-strict-layout")\n        argv.append("--strict-tool-isolation" if self.strict_tool_isolati'
```
