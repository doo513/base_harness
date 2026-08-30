# Base Harness V2 Coordinator Delivery

Date: 2026-08-31
Branch: `develop`
Scope: V2-only runtime, verification safety, WorkGraph orchestration, Host Coordinator, TUI/headless integration

## Delivery index

1. [V2 Runtime and Interface](01_V2_RUNTIME_AND_INTERFACE.md)
2. [Verification Safety Foundation](02_VERIFICATION_SAFETY_FOUNDATION.md)
3. [WorkGraph and Overlay Orchestration](03_WORKGRAPH_OVERLAY_ORCHESTRATION.md)
4. [Coordinator and Sidecar Protocol v4](04_COORDINATOR_AND_SIDECAR_V4.md)
5. [Host, TUI, Headless, and SDK Integration](05_HOST_TUI_HEADLESS_SDK.md)
6. [Validation and Residual Risks](06_VALIDATION_AND_RESIDUAL_RISKS.md)
7. [Next Module, Security, and Isolation Plan](07_NEXT_MODULE_SECURITY_ISOLATION_PLAN.md)

## Authority boundary

```text
Model / worker / tool output
          |
          v
Host-observed candidate and action
          |
          v
Independent verifier attestation
          |
          v
Coordinator-controlled commit / Ready
```

The actor cannot issue final Ready, forge a Host FailureEnvelope, or commit an unverified worker Overlay.

## Commit scope

The delivery includes the runtime, generated SDK, verifier, tests, themes, configuration, and documentation changes present on `develop`.

`net_monitor.py` is intentionally excluded because it is an unrelated local artifact.
