# 06. Validation and Residual Risks

## Situation

The implementation spans generated SDK code, TypeScript packages, a Python sidecar, Host routing, TUI rendering, worker isolation, and Windows-specific execution behavior.

## Reason

Completion claims must distinguish directly validated behavior from unrelated or pre-existing repository debt.

## Action

The final targeted gate executed:

```text
core typecheck + orchestration/secret tests
verification typecheck + package tests
coordinator typecheck + scheduler test
Host typecheck + event/retry/exploration tests
TUI typecheck + theme tests
Python sidecar tests
representative prompt lifecycle tests
CLI help smoke
direct-import boundary scan
```

## Result

The Coordinator delivery passed its targeted gate. The broad repository suite is not declared fully green because unrelated TUI configuration migration, stale OpenCode branding expectations, and Windows timing debt remain.

## Evidence

| Gate | Result |
|---|---:|
| Core tests | 5 passed |
| Verification tests | 14 passed |
| Coordinator tests | 1 passed |
| Host event/retry/exploration tests | 66 passed |
| TUI theme tests | 8 passed |
| Python sidecar tests | 22 passed |
| Representative prompt tests | 4 passed |
| Total targeted tests | 120 passed |

## Residual risks

- The local executable is Bun `1.4.0`, while the repository pins `1.3.14`; Windows prompt tests approach the default five-second test timeout but pass with a 20-second bound.
- TUI configuration precedence and migration tests require a separate focused audit.
- Several inherited test expectations still reference OpenCode branding.
- Native Windows process and filesystem isolation remains weaker than the planned PlatformAdapter/sandbox boundary.
- Candidate materialization copies the workspace and can be expensive for large repositories.
- Root Host shell remains a trusted high-authority boundary until OS sandbox work is complete.

No claim is made that the entire repository is release-ready solely from this targeted gate.
