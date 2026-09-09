# Core runtime regression pass with pending test types (2026-09-08)

## Situation

The prior Git discovery follow-up fixed three runtime failures but introduced a syntax error in the new Git test file. This prevented that file from loading and blocked the Core typecheck.

## Reason

Inserted Bun shell source contained a dollar-backtick sequence. Passing that source as the replacement string to String.replace caused substitution of the original source prefix. Literal insertion requires a replacement callback.

## Action

- Repaired only runtime/packages/core/test/git.test.ts, replacing the known malformed insertion literally.
- Constructed the alternate Windows path with split(path.sep).join("/") instead of ambiguous escaping.
- Preserved the previously implemented native Git discovery and catalog Object.is assertion.
- Ran the Git and catalog tests, Core typecheck, full Core runtime tests, and Host typecheck.

No additional production source changes were made in this step.

## Result

| Gate | Result |
| --- | --- |
| Git and catalog targeted tests | 20 pass, 0 fail; 62 assertions |
| Core full runtime tests | 1109 pass, 7 skip, 0 fail |
| Core full runtime scope | 1116 tests across 146 files; 3046 assertions |
| Host typecheck | Exit 0 |
| Core typecheck | Exit 2; three TS2769 errors in the new Git tests |

The full Core runtime run took 231.65 seconds. The earlier full baseline had 1082 pass, 7 skip, and 18 fail. Nine tests have been added across the intervening repairs. These are comparable full-package runtime runs, not a sum of unrelated targeted runs.

All six new Git discovery fixtures now execute successfully, covering nested discovery, ceiling exclusion, starting at a ceiling, a nearer repository, linked-worktree metadata, and bare-repository rejection. Existing Git clone, synchronization, worktree, and snapshot tests also execute again.

The syntax defect is resolved. The newly visible type errors are at test/git.test.ts lines 95, 114, and 115: expected strings are compared to branded AbsolutePath values. Those three expected values should be constructed with AbsolutePath.make, preserving the equality assertions rather than using unsafe casts. This correction has not yet been applied.

## Evidence

- Pinned repository-local Bun 1.3.14 on Windows.
- BASE_HARNESS_DISABLE_MODELS_FETCH=true and BASE_HARNESS_PURE=1.
- Targeted summary: GIT_TEST_REPAIR tests=0 typecheck=2.
- Full runtime summary: CORE_RUNTIME_AFTER_DISCOVERY_REPAIR tests=0.
- Host summary: HOST_TYPES_AFTER_GIT_DISCOVERY_REPAIR exit=0.
- Companion diagnostic JSON: CORE_RUNTIME_REGRESSION_PASS_TYPECHECK_PENDING_2026-09-08.json.
- The full runtime command retained the last 160 output lines, including totals and skipped cases. It is not a complete per-test raw log.

These results are developer-run diagnostics, not Harness Evidence/Ready or independent user validation.

## Residual Risk

- The Core promotion gate remains failing until the three test type errors are corrected and typechecking passes.
- Seven cases remain skipped: one symlinked-.git watcher case and six PTY cases.
- Some tests have platform-conditional early returns. Passing counts do not establish Windows, WSL, and Linux parity.
- Native Git discovery honors Git configuration; discovery ceilings are not an OS sandbox or an authorization boundary.
- Bare repositories are intentionally unavailable as working trees. File-path or not-yet-existing-directory callers need separate compatibility assessment.
- Real OAuth accounts, genuine model workload quality, standalone distribution, and long-duration stability are not proven by these tests.
- No commit or push was performed. net_monitor.py was not touched.

