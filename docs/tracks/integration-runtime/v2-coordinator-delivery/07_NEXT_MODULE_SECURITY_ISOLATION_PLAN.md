# 07. Next Module, Security, and Isolation Plan

## Objective

Raise module-boundary clarity, maintainability, secret safety, and execution isolation without weakening the Coordinator/verifier authority model.

## Phase 1. Module boundary enforcement

1. Define the allowed dependency graph as `core <- coordinator -> verification`, `host -> coordinator`, and `TUI/headless -> Host API`.
2. Split Coordinator contracts, scheduler, candidate service, event observer, repair router, and run repository into separate modules.
3. Move process-free domain types into a small contracts package that does not import Host, TUI, SDK, or Python process code.
4. Remove remaining cross-package internal-path imports and expose package-root public APIs.
5. Add an import-lint rule that rejects forbidden edges in CI.
6. Add cycle detection for TypeScript workspace packages.
7. Mark generated SDK directories as generated-only and prevent manual edits.
8. Add ownership metadata for integration-only files, protocol schemas, generated files, and package entrypoints.
9. Add boundary tests proving TUI/headless cannot instantiate verifiers or mutate orchestration state.
10. Produce a dependency graph artifact and an exception ledger for unavoidable transitional edges.

## Phase 2. Maintainability and security hardening

1. Replace Coordinator singleton mutable Maps with a run repository interface and explicit scoped lifecycle.
2. Separate state transitions from side effects so scheduler decisions can be deterministically unit-tested.
3. Replace repeated status object mutation with typed transition functions and exhaustive outcome handling.
4. Centralize FailureEnvelope creation at model gateway, tool host, workspace, verifier, and harness producer boundaries.
5. Remove retry and FailureKind decisions based on natural-language strings except unknown fallback telemetry.
6. Register credentials, OAuth tokens, provider options, and sensitive environment values in one SecretRegistry lifecycle.
7. Apply the same redactor before logs, TUI persistence, NDJSON, manifest, Evidence, and Ready writes.
8. Reject persistence when the sidecar residual scanner detects a likely unredacted secret.
9. Add bounded event queues, output-size limits, and artifact-size limits to prevent memory and disk exhaustion.
10. Add protocol schema fuzzing for malformed NDJSON, oversized payloads, duplicate IDs, and invalid scope lineage.
11. Add dependency and license scanning for the forked runtime and bundled binaries.
12. Add explicit deprecation dates for compatibility fields and remove expired legacy configuration paths.
13. Add structured observability for phase time, model calls, tool calls, verification time, repair count, and candidate copy cost.
14. Add run-level budgets that terminate safely without turning budget exhaustion into a code repair request.
15. Document all trusted computing base components and the consequence of each component failure.

## Phase 3. Execution and OS isolation

1. Introduce `PlatformAdapter` interfaces for process groups, termination, paths, file identity, symlinks, junctions, and signals.
2. Implement Linux process-group termination and Windows Job Object termination behind the same contract.
3. Move worker read/write/edit operations behind an Overlay filesystem service with no direct Host path access.
4. Keep exploration workers read-only and deny shell, argv, write, edit, task, web, and network tools at both permission and execution boundaries.
5. Run implementation worker commands only in disposable sandbox backends after structured-tool isolation is stable.
6. Support WSL2 or container isolation first, with a fail-closed Windows native mode when equivalent controls are unavailable.
7. Mount only declared read sets and writable Overlay paths into the sandbox.
8. Deny network by default and add per-WorkUnit destination policies when network access is required.
9. Pass credentials through short-lived scoped channels instead of inherited process environments.
10. Prevent access to Host home, SSH, cloud credentials, browser profiles, Docker socket, named pipes, and unrelated drives.
11. Validate symlink, junction, hardlink, case-folding, UNC, and device-path escapes before every materialization and commit.
12. Add resource limits for CPU, memory, process count, file count, output bytes, and execution time.
13. Record sandbox backend, image/version, mount policy, network policy, and resource limits in the run manifest.
14. Treat sandbox startup failure or policy mismatch as `harness_error` or `sandbox_required`, never implementation failure.
15. Preserve verified committed units when another isolated unit fails, while withholding root Ready.

## Phase 4. Validation and rollout

1. Add module import, package cycle, and public API snapshot tests.
2. Add redaction tests with arbitrary variable names, encoded tokens, short secrets, URLs, and structured objects.
3. Add adversarial protocol tests for actor-forged FailureEnvelope, Evidence, attestation, and Ready artifacts.
4. Add Windows junction/case/UNC and Linux symlink escape tests.
5. Add process-tree cleanup tests for normal completion, timeout, cancellation, verifier crash, and Host crash.
6. Add sandbox tests proving undeclared reads, writes, network access, and credential access are denied.
7. Compare sandbox and non-sandbox outcomes in shadow mode before making isolation authoritative.
8. Measure startup, candidate copy, verifier, repair, and total task latency against the current baseline.
9. Promote each boundary only after targeted tests, TypeScript/Python checks, Windows/Linux integration tests, and artifact review pass.
10. Keep the previous authoritative path available only during shadow comparison, then delete it before release.

## Expected impact

| Area | Expected improvement | Primary cost |
|---|---|---|
| Module boundaries | Lower coupling and clearer ownership | Package/API migration |
| Maintainability | Deterministic transitions and smaller testable services | Refactor volume |
| Security | Unified failure provenance and secret handling | More strict persistence failures |
| Isolation | Reduced Host blast radius | Sandbox startup and copy cost |
| Reliability | Cross-platform process cleanup and fail-closed behavior | Platform-specific implementation |
| Performance | JIT services and bounded queues offset orchestration cost | Measurement and tuning work |

The recommended execution order is Phase 1, Phase 2, Phase 3, and Phase 4. Isolation should not be implemented before module ownership and failure provenance are stable.
