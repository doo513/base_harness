# TUI path display and regression gate repair (2026-09-08)

## Situation

The broader package gates passed for Kernel, KernelHost, Coordinator, and Verification, but the full TUI baseline had 270 passed, 1 skipped, and 7 failed tests across 52 files. Four failures were stale inline-tool snapshots; the other failures concerned sound-pack branding, a collapsed file-tree label, and home-path abbreviation.

## Reason

The runtime path display used the client's native path rules. A Windows TUI attached to a Host using POSIX paths could therefore display a home-relative path with the wrong separator. Other failures were outdated expectations after product-name changes, not evidence of a verifier failure.

## Action

- Updated runtime/packages/tui/src/runtime.tsx to select POSIX or Windows path rules from the supplied home-path syntax.
- Preserved relative-home native fallback and kept the helper presentation-only.
- Added POSIX case and literal-backslash assertions plus Windows drive, separator, sibling-prefix, case, and UNC display cases in test/runtime.test.tsx.
- Updated the sound-pack expectation in test/config.test.tsx to base-harness.default.
- Updated the collapsed directory expectation in test/feature-plugins/diff-viewer-file-tree-utils.test.ts to base-harness/src.
- Regenerated inline-tool snapshots with pinned Bun 1.3.14 after inspecting the baseline differences.
- Ran the complete TUI test suite normally, without snapshot-update mode, followed by the TUI typecheck.

## Result

| Gate | Result |
| --- | --- |
| TUI baseline | 270 pass, 1 skip, 7 fail; 278 tests; 819 assertions |
| Snapshot regeneration | 17 pass, 0 fail; 8 snapshots generated |
| TUI final normal run | 286 pass, 1 skip, 0 fail; 287 tests across 52 files |
| TUI snapshots and assertions | 8 snapshots; 836 assertions |
| TUI typecheck | Exit 0 |
| Kernel | 8 pass, 0 fail; typecheck exit 0 |
| KernelHost | 86 pass, 0 fail; typecheck exit 0 |
| Coordinator | 46 pass, 0 fail; typecheck exit 0 |
| Verification | 25 pass, 0 fail; typecheck exit 0 |

The four non-TUI package suites total 165 passing tests and 1331 assertions. These results are separate scoped gates, not a statement that every repository suite passed.

The existing skipped case remains: DiffViewerFileTree > renders sorted hierarchical file rows.

## Evidence

- Runtime: repository-local .tools/bun-1.3.14/bun.exe.
- TUI command directory: runtime/packages/tui.
- Environment: BASE_HARNESS_DISABLE_MODELS_FETCH=true and BASE_HARNESS_PURE=1.
- Normal TUI command: bun test --timeout 10000.
- Typecheck command: bun run typecheck.
- Final command result: GATE_RESULT tests=0 typecheck=0.
- Companion diagnostic JSON: TUI_PATH_DISPLAY_REGRESSION_REPAIR_2026-09-08.json.
- Captured tool output was truncated in one intermediate chunk; the final test totals and terminal exit status were retained.

These are developer-run diagnostic results, not Harness Evidence, Ready attestations, or independent user validation.

## Residual Risk

- Path abbreviation is display logic, not filesystem canonicalization, sandbox enforcement, or access control.
- A double-leading slash is treated as UNC; this is not a general URI or remote-path parser.
- The existing skipped rendering test remains unvalidated.
- Real OAuth accounts, genuine model workload quality, long-duration operation, and general complex-project performance were not tested by these gates.
- Complete repository, cross-platform isolation, packaging, CJK, resize, and live changed-workspace history coverage remain outside these results.
- Existing verification policy and completion authority were not changed.
- No Git commands, commit, or push were performed in this repair step. net_monitor.py was not touched.

