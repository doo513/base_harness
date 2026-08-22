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
 src/harness/tui_visual.py   |  9 +++++
 3 files changed, 96 insertions(+), 32 deletions(-)
```

## Last log
```text
error: src/harness/tui_visual.py: expected fragment not found: '    acceptance: tuple[str, ...] = ()\n    session_env: dict[str, str] = field(default_factory=dict, repr=False)\n'
```
