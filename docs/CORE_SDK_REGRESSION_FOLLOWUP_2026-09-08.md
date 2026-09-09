# Core and SDK regression follow-up (2026-09-08)

## Situation

After the TUI gate was repaired, a broader Core run returned 1082 passed, 7 skipped, and 18 failed tests across 146 files. Core typechecking initially passed. The SDK package returned 1 passed test and a passing typecheck.

This follow-up is incomplete. A targeted run after the changes returned 84 passed and 3 failed tests; the new catalog identity assertion also introduced a TypeScript error.

## Reason

The baseline failures fell into distinct groups:

- Temporary-directory and Cloudflare User-Agent expectations still used the former product name.
- Project-cache fixtures wrote .git/opencode, but the runtime reads .git/base-harness.
- ModelsDev tests assumed an implicit remote cache. The current runtime defaults to a bundled catalog and only reads a remote cache after explicit configuration.
- A successful candidate fixture omitted materialization, which is now required to bind candidate bytes to the verification workspace.
- A stdout-merging test used echo, whose quoting differs on Windows.
- Three non-Git scenarios unexpectedly discovered the developer's ancestor checkout. A read-only marker check found .git at the user-home level above the system temporary directory.

## Action

Only the following eight test files were edited; no production implementation was changed:

1. runtime/packages/core/test/global.test.ts: expect the base-harness temporary directory.
2. runtime/packages/core/test/preload.ts: append the canonical system temporary directory to test-process GIT_CEILING_DIRECTORIES.
3. runtime/packages/core/test/models.test.ts: explicitly configure the mocked remote source, create a disposable cache, restore process-global settings, and add a default-local/no-refresh case.
4. runtime/packages/core/test/orchestration.test.ts: materialize candidate bytes in success and conflict fixtures; add missing-workspace and changed-verification-bytes rejection cases.
5. runtime/packages/core/test/project.test.ts: use the base-harness cache marker, including the assertion that resolution does not write that marker.
6. runtime/packages/core/test/effect/cross-spawn-spawner.test.ts: produce stdout through the existing JavaScript child helper instead of platform-dependent echo.
7. runtime/packages/core/test/plugin/provider-cloudflare-ai-gateway.test.ts: update only the product User-Agent expectation.
8. runtime/packages/core/test/plugin/provider-cloudflare-workers-ai.test.ts: update only the product User-Agent expectation.

Arbitrary caller metadata still containing the former name was deliberately preserved. It is input data, not application branding to rewrite.

The catalog fixture now avoids removing or overwriting the process's ordinary model cache during its tests. The baseline fixture previously referenced Global.Path.cache directly; this report does not claim that its earlier operations were isolated.

## Result

| Gate | Result |
| --- | --- |
| Full Core baseline | 1082 pass, 7 skip, 18 fail; 1107 tests; 3002 assertions |
| Initial Core typecheck | Exit 0 |
| SDK | 1 pass, 0 fail; 1 assertion; typecheck exit 0 |
| Targeted Core after edits | 84 pass, 3 fail; 87 tests across 9 files; 174 assertions |
| Core typecheck after edits | Exit 2: TS2769 in models.test.ts:152 |
| Post-edit full Core rerun | Not performed |

The remaining failing tests are:

- ProjectV2.resolve > returns global for non-git directory.
- ProjectCopy > refresh ignores existing directories that are no longer git checkouts.
- Snapshot > treats capture outside Git as unavailable.

The new type error is in the test assertion, not a production edit: imported JSON has widened string literals, whereas Bun's typed toBe expects the inferred ModelsDev provider type. The proposed follow-up is a boolean Object.is identity assertion, not an unsafe cast claiming schema validity.

The attempted environment boundary was insufficient. Source inspection shows Git.repo.discover first calls FSUtil.up without a stop boundary, selects the ancestor .git, and then launches Git with cwd already moved to that ancestor. The Git environment ceiling cannot undo that earlier filesystem traversal.

## Evidence

- Runtime: repository-local Bun 1.3.14 on Windows.
- BASE_HARNESS_DISABLE_MODELS_FETCH=true; BASE_HARNESS_PURE=1.
- Full Core tests: 234.53 seconds; CORE_GATE tests=1 typecheck=0.
- Targeted Core tests: 51.87 seconds; CORE_TARGETED_GATE tests=1 typecheck=2.
- SDK: SDK_GATE tests=0 typecheck=0.
- Companion diagnostic JSON: CORE_SDK_REGRESSION_FOLLOWUP_2026-09-08.json.
- Baseline output included a large catalog diff and was truncated in an intermediate tool response. The terminal summary retained all 18 failing test names.
- Targeted output retained the final 160 lines, all remaining failure names, final totals, and the type error.

These results are developer-run diagnostics, not Harness Evidence, Ready, or independent user validation. Matching candidate attestation fields in these unit fixtures do not prove a real verifier ran.

## Residual Risk

- The newly introduced test type error remains unresolved in this revision and was disclosed.
- Test-process ceiling configuration does not yet constrain the custom filesystem discovery walk.
- Follow-up should enforce discovery limits before selecting an ancestor, while preserving ordinary nested repositories and linked worktrees. Do not remove or change the user's home .git.
- FSUtil.up already accepts a stop path, but its boundary is inclusive. A ceiling implementation must handle that distinction explicitly and cover canonical paths and Windows casing.
- Seven baseline skips remain unverified: one symlinked-.git watcher case and six PTY cases.
- Some platform tests return early on unsupported systems; a passing count alone does not prove cross-platform coverage.
- SDK coverage consists of one history-position test and static typechecking, not full endpoint behavior.
- No real OAuth account or production model workload was validated here.
- No repository commit or push was performed, and net_monitor.py was not touched. Existing tests invoke Git for repository/worktree fixtures.

