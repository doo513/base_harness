# Scoped Tool Catalog Alignment and Validation Limits

Date: 2026-09-08
Status: Implemented; selected local checks passed. General user reliability remains unproven.

## Situation

Managed worker requests advertised shell, MCP and other tools that their execution policy already rejected. This was a catalog/execution mismatch, not a demonstrated host privilege bypass. The registry's existing GPT-family patch preference could also remove edit/write even when a worker could not use apply_patch. Exploration's workspace guard was broader than the intended inspection-only policy.

## Reason

Model-visible tools should be a projection of the actual scope policy. Advertising unavailable actions wastes model decisions and can turn a workable task into repeated permission failures. Schema visibility is not authorization: invocation-time scope, ownership and budget guards remain required.

## Action

- Added filterToolsForScope in runtime/packages/workspace/src/orchestration.ts, deriving scoped visibility from the existing execution guard instead of a second catalog allowlist.
- Restricted running exploration and meta-review scopes to read/list/glob/grep; closed inspection scopes expose no tools.
- Passed session identity into runtime/packages/base-harness/src/tool/registry.ts and retained structured editors when patch is unavailable to the scope.
- Filtered builtin schemas before tool-definition processing. Unexpected persistence/policy failures propagate rather than producing a successful empty catalog.
- In runtime/packages/base-harness/src/session/tools.ts, reran contract/scope guards before the builtin plugin before-execution hook and omitted MCP schemas from managed child sessions.
- Added eight scope-catalog regression tests and extended runtime/script/verify-provider-public-boundary.mjs with an optional two-WorkUnit planned fixture.
- Preserved root/unmanaged tool behavior and existing invocation-time checks.

## Result

Eight selected tests passed with 40 assertions. Workspace, Coordinator and Host typechecks passed using Bun 1.3.14.

A real local Host/headless run with a deterministic authenticated provider, local MCP and Python verifier completed two WorkUnits. All four actual worker model requests advertised exactly edit, glob, grep, read and write. Both workers retained usable structured editors and completed without repair. Goal and plan reviewers advertised glob, grep and read.

Both output files matched the fixture's expected bytes. Root status reported adaptive Ready with four evidence observations. The stored root Ready attestation reported full coverage and verified results for claim-0/criterion-0 and claim-1/criterion-1. These claims concern exact file contents, not general harness correctness.

Public provider metadata still omitted credentials/private options while preserving exact high/max effort names. All fixture model requests used authenticated private execution with native effort high.

## Evidence

- Selected gate log: .tools/validation/restoration-phase42-scoped-tool-catalog-gates.log
- Runtime diagnostic: .tools/validation/restoration-phase42-scoped-worker-catalog.result.json
- Test source: runtime/packages/workspace/test/scoped-tool-catalog.test.ts
- Session: ses_f816bd9aeffeL4wsLJNQLCS7d9
- Run: run-d01adc5c-1586-4ed2-8212-79236ecd39ff
- Root Ready artifact: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-wM5EXO/state/base-harness/runs/6cf1165e748cc3fb-0a34fa51/artifacts/97/97cd44fab9e79847525772d9c22b79aea95145ecacaa771a893c24ff2a31d471.json
- Companion diagnostic summary: docs/evidence/SCOPED_TOOL_CATALOG_ALIGNMENT_2026-09-08.json

The client exited 0. The fixture intentionally terminated its Host, which exited 143. No managed process handle remained live in the recorded run.

Single-sample observations: health startup approximately 9.45 seconds, first provider listing 2.10 seconds, client execution 28.20 seconds. These are not a performance benchmark or evidence of a speedup.

## Residual Risk

- Tests and fixtures were authored by the same implementation agent. They can share assumptions or omissions with production code.
- The Python verifier is a separate runtime authority for the declared file predicates, not an independent human or independent design review of this harness.
- A scripted provider does not test actual model decision quality, real OAuth renewal, rate limits, variable latency or long conversations.
- Actual GPT-family behavior was not exercised. The scope-aware editor fallback has targeted coverage, not real-provider acceptance.
- Two completed workers do not by themselves establish a scheduler concurrency timing guarantee.
- This run did not exercise a rejection/repair loop, cancellation stress, malicious plugins, cross-platform sandboxing, or the complete regression suite. No new TUI runtime/typecheck gate was executed in this phase.
- Root shell privileges and trusted plugin initialization are separate boundaries; this change is not an OS sandbox.
- Catalog membership does not authorize every argument. Path ownership and budgets must still be checked at invocation.
- The fixture contract records unknown config/dependency/workspace revision hashes. Do not reuse its Ready as proof for another environment.
- The earlier phase38 titlecase expectation mismatch and phase40 short readiness-timeout diagnostic remain unresolved and unchanged. Later successful fixtures do not erase those failures.
- No Git commands, commits or push were performed. net_monitor.py was untouched.

## Next User-Reliability Gates

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Real provider connection | User-selected provider login, model/effort switching, disconnect/reconnect without secret persistence | Not established by this fixture |
| Unscripted representative work | Previously unseen tasks, external acceptance criteria and independently checked outputs | Not established |
| Failure recovery | Controlled provider failure, rejected candidate, bounded local repair and cancellation with preserved work | Not exercised here |
| Long-session behavior | Repeated tasks and context compaction with latency/resource observations | Not exercised here |
| Interface parity | Equivalent live TUI/headless tasks and restored sessions under the same Host policy | Prior scoped checks exist; broad parity remains unproven |
| Independent review | Reviewer not responsible for the implementation examines requirements and failure cases | Not established |

The appropriate assessment is "scoped local behavior confirmed", not "production-ready" or a numerical user-reliability score. This document and its diagnostic JSON are engineering records, not Harness Evidence/Ready artifacts.
