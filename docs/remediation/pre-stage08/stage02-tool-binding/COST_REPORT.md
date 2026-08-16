# Stage 02 Remediation — Tool Backend Binding COST REPORT

## Cost objective

The binding fix must not add a second execution or duplicate attestation merely to prove backend identity. The valid strict side-effect path should inspect and invoke one backend object, while an invalid generic-handler mismatch should fail before any side effect.

## Valid sandboxed command path

Expected and directly counted by `scripts/remediation_tool_binding_cost_probe.py`:

```text
attestation calls       1
backend execution calls 1
handler indirections    0
```

Compared with the prior built-in shell convention, this does not add a backend execution call. It removes the host-side handler closure as the side-effect owner and calls the backend directly from `ActionRuntime`.

## Invalid mismatch path

After remediation:

```text
generic ToolSpec + strict WRITE/EXTERNAL
-> type/binding rejection
-> attestation calls 0
-> backend executions 0
-> unsafe handler calls 0
```

This is cheaper than the former vulnerable path, which performed an attestation and then an unrelated handler call.

## CPU / I/O / wall time

No additional file hashing, mount topology scan, subprocess, or external call is introduced for a valid sandboxed command beyond the existing attestation + backend execution pair.

The new checks are constant-time Python type/argument/policy checks. Wall-time microbenchmarking is not treated as meaningful because actual backend subprocess/sandbox execution dominates.

## Tokens

No additional model-visible context is introduced. Prompt token cost change: **0**.

## Tool calls

Harness Actor-visible tool-call count is unchanged. A valid tool request still produces one tool execution. The internal backend call count remains one.

## Persistence / event growth

No new HarnessState, checkpoint, receipt, or event type is introduced. Existing tool result/receipt semantics are reused.

## Provenance cost

Four small strings are added to the existing Tool provenance descriptor for sandboxed command tools:

```text
execution_kind
command_arg
timeout_seconds
require_zero_exit
```

They are computed once at spec construction and serialized as part of the existing run configuration fingerprint; there is no per-turn recomputation.

## Cost judgment

The fix closes a reproduced isolation bypass without adding backend calls or model tokens on valid execution. Invalid mismatched tools now terminate earlier and cheaper. The integrity benefit clearly exceeds the negligible policy/type-check overhead.
