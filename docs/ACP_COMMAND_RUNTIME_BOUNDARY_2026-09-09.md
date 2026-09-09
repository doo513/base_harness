# ACP Command Runtime Boundary

## Situation

The ACP CLI used effectCmd with instance=false. That option skipped project bootstrap but still imported and acquired the complete AppRuntime. The ACP handler subsequently started a Host HTTP server whose listener manages its own Effect runtime.

## Reason

The transport command needs global configuration to resolve network options, not the entire agent service graph. Removing that command-level dependency separates transport lifecycle from Host execution ownership without returning a fabricated initialization response or increasing deadlines.

## Action

- Changed the ACP command wrapper to cmd and an explicitly scoped Effect runner.
- Provided the Config service dependency graph and Observability layer to the command handler.
- Retained the existing resolveNetworkOptions implementation and configuration precedence.
- Kept Host server creation, SDK transport, agent disposal, server cleanup, and the early stdin EOF guard.
- Left provider behavior, Coordinator, verifier, completion policy, and request timeouts unchanged.
- Did not modify net_monitor.py or perform Git operations.

## Result

Host type checking passed. The focused ACP run passed 17 tests with 112 assertions across three files in 63.65 seconds, with no failures.

## Evidence

Developer diagnostics only: diagnosticOnly=true, notHarnessEvidence=true, notIndependentUserValidation=true.

- Runtime: repository-bundled Bun 1.3.14.
- Working directory: runtime/packages/base-harness.
- bun run typecheck: exit 0.
- bun test --timeout 30000 --only-failures test/cli/acp-input.test.ts test/cli/acp/lifecycle.test.ts test/cli/acp/config-options.test.ts: exit 0.
- The tests exercise actual CLI subprocesses for EOF, session lifecycle, and model configuration behavior alongside deterministic input tests.
- No paid model calls or authentication changes were performed.

## Residual Risk

This removes the explicit full-AppRuntime acquisition from the ACP command. Host server imports and acquisition still have a startup cost; this is not a claim that every heavy dependency is now lazy or that process startup is cheap. The long full-suite live-child initialization timeout has not been rerun or proven fixed. Focused developer tests do not establish independent end-user, OAuth, TUI, or cross-platform stability. No before/after performance improvement is claimed from this run.
