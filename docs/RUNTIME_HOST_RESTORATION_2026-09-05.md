# Runtime Host Restoration

## Situation

The current default CLI used a minimal replacement runtime while the existing
Kernel, Coordinator, planning, Overlay and security implementations remained in
workspace packages. The replacement path bypassed these facilities.

## Reason

Restoring policy ownership is preferable to recreating a second verification
model or duplicating authentication and tool execution in a new TUI.

## Action

- Archive the minimal prototype without deleting its source.
- Restore the workspace manifest and launch the bundled Host from one thin CLI.
- Extract KernelHost, Workspace and Security packages; retain re-export bridges.
- Require actual verifier acceptance before contracts permit execution.
- Preserve claim predicates instead of replacing them with a generic exit-code check.
- Isolate Candidate stores by async execution context and serialize commits.
- Match sidecar response run/scope identity and reject premature exit.
- Restrict the verifier process environment and pass trusted failure metadata.
- Move TUI capability discovery and automatic verification ownership to Host.
- Add targeted regression fixtures for restoration boundaries.

## Result

Implementation changes are prepared for execution verification. This document
does not claim a passing suite or a working paid provider connection.

## Evidence

Authoritative evidence must come from the targeted KernelHost, Coordinator,
Workspace and verification tests, package typechecks, CLI startup, and actual
Host/TUI workflow exercises. Their outcomes are not assumed from source review.

## Residual Risk

- OAuth and real provider availability require a live connection check.
- Namespace/WSL containment requires platform-specific execution tests.
- Existing execution adapters and compatibility bridges still need boundary audit.
- The shared-model meta reviewer can have common-mode errors.
- No commit or push is performed as part of this restoration step.
- Pre-existing edits and untracked net_monitor.py are preserved.
