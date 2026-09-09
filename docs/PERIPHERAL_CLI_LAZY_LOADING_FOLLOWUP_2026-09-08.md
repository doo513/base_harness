# Peripheral CLI Lazy Loading and Host Runtime Follow-up

## Situation

Source-based startup remained variable. Before this change, one untraced Host attempt exceeded the unchanged 30-second health deadline after 30.172 seconds without sending a model request. A separate traced attempt reached health readiness in 17.365 seconds. Those observations do not establish a single root cause.

The CLI entry point eagerly imported the debug command tree and ACP command even when another command was selected.

## Reason

Keep unrelated command dependencies out of the initial entry-point import graph. Reuse the existing lazy-command adapter rather than change command identity, runtime service ownership, verifier behavior, or readiness semantics.

This is a bounded startup improvement, not a replacement for real-account testing or a claim that all startup stalls are resolved.

## Action

- Replaced static debug and ACP imports in `runtime/packages/base-harness/src/index.ts` with lazy loaders.
- Added their public identities to `src/cli/entry-command-metadata.ts`; command implementations consume the same metadata.
- Preserved command registration order, nested command behavior, global options and existing help contracts.
- Added lazy-command coverage for root help without loading peripheral modules, nested dispatch and asynchronous nested help.
- Did not change AppRuntime layers, Server readiness, model reasoning identifiers, verifier policy or timeout limits.
- Did not modify `net_monitor.py`; no commit or push was performed in this phase.

## Result

| Check | Result |
| --- | --- |
| CLI lazy-command and startup-trace tests | 20 passed, 0 failed; 64 assertions across 2 files |
| Host typecheck | Exit 0 |
| Root help | Exit 0; 5.499 seconds |
| Debug help | Exit 0; 4.035 seconds |
| ACP help | Exit 0; 3.697 seconds |
| Debug paths | Exit 0; 3.982 seconds |
| Untraced actual Host fixture | Ready; health startup 8.076 seconds |
| Traced actual Host fixture | Ready; health startup 7.817 seconds |

All four CLI checks omitted runtime service startup. The expected command-builder mismatch diagnostic belongs to a passing rejection test, not a failed gate.

Both actual Host runs used the source launcher, local deterministic model/MCP services and the real Python verifier. Each made 14 scripted model requests, completed two WorkUnits and repaired unit-0 once in its existing child session. Unit-1 wrote once. The rejected unit-0 candidate was absent from the base workspace before repair. Final root status was Ready with planning idle.

Public provider metadata omitted credentials/private options and retained exact `high` and `max` identifiers. Fixture execution authenticated successfully. This does not establish compatibility with a real subscription account.

The traced run observed 3.980 seconds for entry imports, 1.273 seconds for runtime imports and 0.656 seconds for Host imports. Earlier traced spans were 7.040, 6.235 and 2.196 seconds respectively. These are unpaired observations, not a controlled benchmark or proof that lazy loading caused the entire difference.

## Evidence

These are developer diagnostic records, not independent user validation or new Harness Evidence.

- Companion summary: `docs/PERIPHERAL_CLI_LAZY_LOADING_DIAGNOSTICS_2026-09-08.json`.
- Untraced raw result: `.tools/validation/lazy-peripheral-host-1788845075709.result.json`.
- Traced raw result: `.tools/validation/lazy-peripheral-host-trace-1788845208253.result.json`.
- Startup trace: `.tools/validation/lazy-peripheral-host-trace-1788845208253-host.stderr.log`.
- Untraced run ID: `run-5691d6b2-908d-4e7a-a05a-49eee3bf9253`.
- Traced run ID: `run-c2be1e08-60e7-468b-95ed-fe325a050d2b`.
- Previous failure and traced baseline: `docs/GIT_TYPE_REPAIR_AND_HOST_STARTUP_OBSERVATION_2026-09-08.md`.

The companion JSON sets `diagnosticOnly`, `notHarnessEvidence` and `notIndependentUserValidation` to true. Ready artifacts produced by the real verifier remain scoped to the fixture's file-content contract. They do not certify the product's general reliability.

## Residual Risk

- Startup variability remains open; two successful attempts do not invalidate the preceding timeout.
- Warm caches, machine load and trace overhead were not controlled.
- Runtime service initialization and remaining eager imports still contribute startup cost.
- Actual ACP protocol sessions were not exercised; ACP help only was checked.
- Real OAuth/provider accounts and genuine LLM planning quality/cost were not assessed.
- The full Host suite and native TUI visual/platform matrix were not rerun in this phase.
- Host exit code 143 reflects intentional fixture cleanup, not proof of complete descendant-process cleanup.
- Windows/WSL/Linux isolation and standalone packaging remain separate unfinished work.
