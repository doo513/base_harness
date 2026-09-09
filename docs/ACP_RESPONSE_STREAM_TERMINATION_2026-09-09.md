# ACP Response Stream Termination

## Situation

The CLI subprocess test transport buffered ACP responses without closing its queue when stdout ended or failed. A receive could therefore wait until the request deadline after the transport had already terminated.

## Reason

An ended transport must be distinguishable from a live but slow startup. Buffered responses must remain available before terminal failure is reported. This correction does not explain the separate long-suite initialization timeout in which the child remained alive.

## Action

- Added a scoped response reader that closes the queue on stream completion, failure, or interruption.
- Added typed ACP_STDOUT_CLOSED and ACP_STDOUT_FAILED errors to the test handle and client.
- Preserved buffered JSON responses, malformed-line diagnostics, and nonempty-line counting.
- Kept transport error messages fixed rather than embedding potentially sensitive underlying errors.
- Added deterministic stream tests and an EOF receive assertion to the real CLI subprocess lifecycle test.
- Left the 15-second request deadline, production gateway, verifier policy, and net_monitor.py unchanged.

## Result

The focused Bun run completed with 5 passing tests, 4 filtered tests, 0 failures, and 22 assertions across 2 files in 14.90 seconds. Host type checking completed with exit code 0.

## Evidence

Developer diagnostic records only: diagnosticOnly=true, notHarnessEvidence=true, notIndependentUserValidation=true.

- Bun version: 1.3.14.
- Working directory: runtime/packages/base-harness.
- Command: bun test --timeout 30000 --only-failures test/cli/acp-responses.test.ts test/cli/acp/lifecycle.test.ts --test-name-pattern "ACP|stdin EOF exits cleanly".
- Command: bun run typecheck (tsgo --noEmit).
- No full-suite rerun, paid model calls, Git operations, or push was performed for this change.

## Residual Risk

This change corrects the test transport and its failure reporting, not a demonstrated production connection defect. The previous full Host suite's live-child initialization timeout remains unresolved. These developer tests do not establish real-user OAuth, interactive TUI, or cross-platform operational stability.
