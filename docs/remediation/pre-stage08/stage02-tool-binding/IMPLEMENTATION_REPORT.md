# Stage 02 Remediation — Tool Backend Binding IMPLEMENTATION REPORT

Status: **red defect confirmed / green implementation confirmed / release freeze pending**

## 1. Finding

The Stage-02 strict tool path previously performed:

```text
inspect spec.execution_backend.isolation_attestation(...)
-> execute spec.handler(...)
```

The backend object and the executed callable were independent objects. A trusted/plugin tool could attach strong backend metadata while its handler performed host-side side effects directly.

Classification: **A — Confirmed code/security defect**.

## 2. Red reproduction

`scripts/stage2_tool_backend_binding_probe.py` creates:

- an attested isolated test backend;
- a generic WRITE ToolSpec carrying that backend as metadata;
- an in-process handler that writes a private canary outside the Actor workspace.

Before the fix, GitHub Actions run `31948573578` showed:

```text
result.ok                              true
result.security_violation              false
unsafe_handler_calls                   1
attested_backend_execution_calls       0
private_canary_changed                 true
attestation_execution_mismatch         true
```

Thus the mismatch was not theoretical: strict isolation authorized one object and executed another.

## 3. Type / execution ownership remediation

### Trusted `ToolSpec`

The existing `ToolSpec` remains available as a trusted in-process/legacy type for compatibility. It is explicitly not an attested sandbox execution object.

In strict isolation:

```text
ToolSpec + WRITE/EXTERNAL
-> BLOCK / security_violation
```

even if `execution_backend` metadata is populated.

### `SandboxedCommandToolSpec`

A distinct declarative type was introduced. It contains:

- execution backend;
- execution workspace;
- timeout;
- command argument name;
- side-effect class;
- permission/idempotency/failure modes;
- declarative zero-exit requirement;
- provenance metadata.

It deliberately provides no executable arbitrary handler/precondition/postcondition path.

### Runtime-owned execution

For `SandboxedCommandToolSpec`:

```text
backend = spec.execution_backend
-> backend.isolation_attestation(...)
-> same backend object
-> backend.run_shell(...)
```

No handler closure is used for the side effect.

`make_shell_tool()` now returns `SandboxedCommandToolSpec`, so the built-in shell path also uses Runtime-owned backend execution.

## 4. Stage-03 provenance preservation

The previous `make_shell_tool()` handler closure indirectly fingerprinted timeout semantics through callable closure provenance. Removing that handler could have weakened resume drift detection.

The new spec therefore injects the following declarative semantics into the existing Tool provenance descriptor:

```text
execution_kind
command_arg
timeout_seconds
require_zero_exit
```

The backend descriptor and execution workspace remain in the existing run config fingerprint.

## 5. Green validation

Green commit/run:

- commit `6792876b09df13f66061f598644cc530e921c35e`
- GitHub Actions `31948805281`

Results:

```text
pytest                              140 passed / 5 skipped
Stage03 resume                      4/4 PASS, duplicate external actions 0
Stage04 semantic                    8/8 PASS, FP=0/FN=0
Stage05                             PASS
Stage06                             PASS
Stage07                             PASS
Stage08 single-buffer               PASS 6/6
Stage02 nested-submount             PASS
backend binding attack:
  unsafe_handler_calls              0
  backend_execution_calls           0
  private_canary_changed            false
  security_violation                true
```

## 6. Unit coverage

`tests/test_stage2_tool_binding.py` verifies:

1. generic WRITE ToolSpec cannot borrow backend attestation in strict mode;
2. valid sandboxed command invokes its backend;
3. attestation and execution happen on the same object identity;
4. non-zero command results preserve tool-failure semantics;
5. non-strict trusted in-process tools remain compatible;
6. declarative execution semantics are included in provenance.

## 7. Guarantee boundary

This remediation binds **declared strict WRITE/EXTERNAL tool execution** to its attested backend.

It does not prove that a malicious trusted registry cannot intentionally misclassify a side-effecting handler as `SideEffect.NONE` or `READ`. Trusted tool registration remains a configuration trust boundary. A future stronger plugin API may further restrict in-process tool capabilities, but that is distinct from the reproduced metadata/execution mismatch.
