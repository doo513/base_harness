# Tool Contract and Sensitive Read Policy Alignment

## Situation
Two known Host failures referenced an obsolete task wire snapshot and the removed plan agent. Inspection also found read-only roles overriding sensitive-file read confirmation with a blanket read allow rule.

## Reason
The current task contract includes structured exploration and WorkUnit binding. Planning is a Kernel control, not a current plan agent. Read-only authority must not implicitly waive confirmation for secret-bearing environment files.

## Action
- Shared the existing sensitive-file read pattern policy between default, explore, and meta-review permissions.
- Kept build/general behavior, read-only mutation denial, and explicit user-policy precedence unchanged.
- Replaced obsolete plan-agent cases with build, general, explore, and meta-review cases.
- Set the tool context agent to the role actually under test.
- Added parse assertions for WorkUnit IDs, structured exploration presets/budgets, and malformed exploration requests.
- Regenerated task/schema snapshots with bundled Bun 1.3.14, then reran without update mode.
- Did not restore the removed plan agent or weaken execution admission.

## Result
- Read and parameter suite: 115 passed, 0 failed, 177 assertions, 2 files, 22.96 seconds.
- Host typecheck: exit 0.
- Clean subsequent parameters run: 61 passed, 0 failed, 16 snapshots checked, 73 assertions, 5.15 seconds.
- The two previously known fixture failures are resolved in these runs.
- Default .env confirmation now applies to explore and meta-review as well as build/general.

## Evidence
- Initial task-only snapshot update: 1 passed, 60 filtered out, 1 snapshot added.
- The subsequent full two-file run regenerated 15 other snapshots and checked the task snapshot. This run alone was not treated as a clean snapshot comparison.
- Final no-update parameters run checked all 16 stored snapshots successfully.
- Combined tests/typecheck session 48280 ended with TOOL_CONTRACT_ALIGNMENT tests=0 typecheck=0.
- Commands: bundled Bun test --timeout 15000 --only-failures test/tool/parameters.test.ts test/tool/read.test.ts; bundled Bun run typecheck; bundled Bun test --timeout 10000 --only-failures test/tool/parameters.test.ts.
- Companion: TOOL_CONTRACT_SENSITIVE_READ_DIAGNOSTICS_2026-09-08.json.

## Residual Risk
- The tests exercise actual ReadTool paths with a fixture permission callback, not interactive TUI approval handling.
- The default filename patterns do not identify every possible credential-bearing file. Explicit user permission overrides remain supported.
- Numeric exploration caps are still enforced by the separate exploration budget runtime; schema acceptance is not budget authorization.
- Three earlier Host failures remain: compaction cancellation timing and two Windows symlink cases.
- Full Host suite completion, its earlier unexecuted remainder, real-provider behavior, and independent user validation remain unproven.
- No repository Git operations or net_monitor.py changes were made.

