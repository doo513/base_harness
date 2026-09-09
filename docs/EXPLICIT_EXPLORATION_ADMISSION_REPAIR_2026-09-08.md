# Explicit Exploration Admission Repair

## Situation
The Host allowed a structured pre-contract explore task, but Workspace rejected it before child-session metadata was created. Coordinator deliberately initialized discovery without heuristic automatic exploration.

## Reason
Workspace began in direct phase and startChild(explore) accepted only exploration phase. Role forwarding alone could not supply the missing transition. Forcing always-explore globally would change simple-task behavior and was not an appropriate repair.

## Action
- Added a typed explicit direct-to-exploration transition for an idle root with no accepted contract or WorkGraph.
- Kept already scheduled exploration supported without introducing natural-language classification.
- Added a per-root explorationScopeId latch and included it in Workspace snapshots.
- Allowed idempotent admission of the same running explorer; rejected another or finished explorer.
- Rejected nested parents, WorkUnit binding, reused scope identity, busy discovery, post-contract direct work, and terminal phases.
- Preserved read-only tool permissions and no candidate/evidence authority for exploration.
- Retained the earlier SessionTools and Registry structured-role forwarding fixes.
- Added isolated Workspace boundary tests; restored the Host fixture's default policy.

## Result
- Workspace targeted regression: 20 passed, 0 failed, 154 assertions, 3 files, 1.191 seconds.
- Workspace typecheck: exit 0.
- Host metadata/busy-idle pair: 2 passed, 0 failed, 57 filtered out, 5 assertions, 13.08 seconds.
- Host typecheck: exit 0.
- Broader Host prompt, snapshot race, and contract admission: 54 passed, 14 skipped, 0 failed, 239 assertions, 68 cases across 3 files, 89.46 seconds.
- The previously reproducible metadata integration failure is resolved in these fixtures.
- No full-suite or independent user-stability claim is made.

## Evidence
- Workspace command: bundled Bun test --timeout 10000 --only-failures test/explicit-exploration-boundary.test.ts test/meta-review-boundary.test.ts test/orchestration.test.ts; bundled Bun run typecheck.
- Host pair session 23635: PID 28692, stopped=true, timedOut=false, exitCode=0.
- Host pair stdout: .tools/validation/explicit-exploration-host-1788860824349.stdout.log.
- Host pair stderr: .tools/validation/explicit-exploration-host-1788860824349.stderr.log.
- Host typecheck session 7878: exitCode=0.
- Broader Host session 24787: PID 3116, stopped=true, timedOut=false, exitCode=0.
- Broader stdout: .tools/validation/prompt-regression-after-exploration-1788860876280.stdout.log.
- Broader stderr: .tools/validation/prompt-regression-after-exploration-1788860876280.stderr.log.
- Companion: EXPLICIT_EXPLORATION_ADMISSION_DIAGNOSTICS_2026-09-08.json.

## Residual Risk
- Five other failures from the earlier bailed Host suite remain: compaction cancellation timing, two Windows symlink cases, task schema snapshot, and obsolete plan-agent env-file fixture.
- The earlier full suite stopped after 20 failures; its unexecuted remainder and later changes still require full regression.
- Older standalone automatic uncertainty heuristics remain outside this patch; no claim of removing all natural-language policy logic.
- Watchdogs were not triggered, so tree-kill behavior was not exercised.
- This repair does not establish genuine OAuth behavior, long-running TUI usability, cross-platform isolation, or independent user validation.
- No Git operation or net_monitor.py modification was performed.

