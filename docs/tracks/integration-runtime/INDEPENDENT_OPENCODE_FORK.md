# Independent OpenCode fork

## Decision

base-harness owns a source snapshot of OpenCode v1.18.23 under runtime/. The
snapshot supplies the TUI, agent runtime, provider/model gateway, MCP, tools,
sessions, plugins, and subagents. No external opencode or gjc process is
started.

The snapshot is a one-time origin, not an upstream synchronization contract.
Automatic updates and OpenCode configuration paths are disabled. Product
configuration is read from base-harness.jsonc.

## Trust boundary

The TypeScript runtime performs work. A separately packaged
base-harness-verifier process decides whether independent evidence satisfies
the root GoalContract.

The stdio protocol is NDJSON. Every envelope has version, id, runId, scopeId,
type, and payload. Requests are hello, run.open, scope.open, action.observe,
verify.request, status.get, and run.close.

Model text and tool output are evidence candidates with
untrusted_execution_observation trust. They cannot create Evidence or Ready.
Only checks launched by the verifier become verifier_observed evidence, and
only the root scope can receive a verifier_attested Ready artifact.

Verifier crashes, malformed NDJSON, protocol mismatch, and timeouts are
fail-closed. The runtime must not show Ready after any of these failures.

## Repair behavior

Adaptive verification runs when tool activity has completed, no tool is
pending, no user question is active, and the session becomes idle. A rejection
returns only FailureKind, the failed criterion, missing evidence, repair scope,
and repair count to the same session.

The full plan is not regenerated. The third occurrence of an identical
failure fingerprint is blocked when maxSameFailureRepairs is 2.

## State and release

Verifier state is outside the workspace in LOCALAPPDATA/base-harness on
Windows and XDG_STATE_HOME/base-harness on Linux. Manifests record protocol
version and execution-core revision.

Release ZIPs contain the Bun-compiled base-harness executable, the
PyInstaller-compiled verifier, base-harness.schema.json, the MIT license, and
UPSTREAM_NOTICE.md. Bun, Python, OpenCode, and Gajae-Code are not runtime
prerequisites.
