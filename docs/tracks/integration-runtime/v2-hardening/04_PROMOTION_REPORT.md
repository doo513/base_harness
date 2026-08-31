# Hardening Promotion Report

## Situation

The V2 runtime had working Coordinator, verification, Overlay, and TUI paths, but ownership, persistence, trusted failure creation, secret redaction, and strict process isolation were not enforced at one boundary.

## Reason

Without executable promotion gates, a UI or actor could bypass the intended authority boundary, a candidate could be committed without matching attestation, secrets could cross persistence surfaces, and strict shell execution could still affect the Host.

## Action

The delivery centralized run ownership in `CoordinatorService`, replaced Core global candidate state with an instance store, added atomic run snapshots and interrupted recovery, introduced a single persistence/redaction path, branded Host-created failures, capped graph/event/artifact resources, and routed strict shell execution through WSL2 or Linux namespaces. Promotion tests now pin the public Coordinator API, candidate attestation, path escape handling, WSL isolation, timeout cleanup, and fail-closed behavior.

Windows Job Object containment was initially attached to every Core child process during the promotion run. That coupling was rejected because it added overhead and risk to Git, NPM, LSP, and internal tools. The final implementation makes Job Object assignment an internal opt-in used only by adaptive user shell execution, removes the marker before spawning the child, and leaves internal process paths unchanged.

## Result

The hardening-specific promotion gate passes. Strict WSL2 execution blocks external network access, permits namespace-local loopback, keeps system paths read-only, restricts writes to the copied candidate, rejects external links, fails closed for missing distros, and removes descendant processes on timeout. Candidate changes remain isolated until a matching verifier attestation and base hash permit commit.

The broad upstream-derived suites are not a green release gate on this Windows checkout. They retain pre-existing Windows timing, stale OpenCode branding, TUI migration, live model-catalog snapshot, and path expectation failures. These failures do not overlap the hardening target tests, but they remain product debt and must not be represented as fixed by this delivery.

The exact `fast` direct-path median delta cannot be stated as a percentage because no pre-change machine baseline artifact existed. The promotion audit instead removed the discovered global Job Object overhead and verified that internal Git/NPM behavior succeeds with a realistic Windows timeout. A versioned benchmark fixture is still required before enforcing the requested 10 percent regression threshold in CI.

## Evidence

- Harness boundary and package-cycle check: pass.
- Public Coordinator API and interrupted recovery: 3 tests passed.
- Candidate attestation, mismatch, and base-hash conflict: 3 tests passed.
- WSL2 policy, external-link rejection, missing backend, and descendant timeout cleanup: 6 tests passed.
- FailureEnvelope/profile/sidecar v4 verification: 15 tests passed.
- Host manifest, exploration, contract, and retry regression: 68 tests passed.
- Adaptive shell execution, permission, path, cancellation, timeout, streaming, and truncation regression: 91 tests passed.
- TUI theme regression: 8 tests passed.
- Python independent sidecar: 22 tests passed on Python 3.12.
- SDK generated contract: 1 test passed; `Config.isolation` is present in legacy and V2 generated types.
- Windows Git/NPM functional retry with a 30 second test timeout: 8 tests passed.
- Core, Coordinator, Verification, Host, SDK, and TUI typechecks: pass.
- `base-harness --help`: exit code 0.
- Targeted promotion evidence total: 234 passing test executions, including repeated post-fix sandbox and process checks.
- Broad Core observation: 1064 passed, 7 skipped, 36 failed, 4 errors; failures are Windows timing, path, live catalog, and stale branding baseline items.
- Broad TUI observation: 186 passed, 1 skipped, 7 failed; failures are stale branding snapshots and Windows path expectations.
- Broad Host observation: stopped after known branding, TUI migration, plugin, Git/worktree, and Windows timing failures produced no new hardening signal.

## Residual Risks

- The repository pins Bun 1.3.14, while this Windows promotion run used Bun 1.4.0.
- The checked-in `.venv` points to a removed temporary Python 3.14 interpreter; sidecar tests required an independent Python 3.12 test environment.
- Adaptive Windows Job Object containment is best effort; strict execution never falls back to that backend.
- Linux namespace behavior is implemented but was not executed on a native Linux host during this Windows promotion run.
- A committed pre-change latency fixture is needed before CI can enforce the 10 percent fast-path threshold.
