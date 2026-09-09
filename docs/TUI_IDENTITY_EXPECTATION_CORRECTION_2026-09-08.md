# TUI Identity Expectation Correction (2026-09-08)

## Situation
The phase-38 presentation gate retained one failure: a new assertion expected Build-tools while the deliberately preserved Locale.titlecase formatter produces Build-Tools.

## Reason
The intended change hid only the exact legacy primary roles build and plan behind Base Harness. It did not change formatting of custom roles. The assertion guessed the existing formatter incorrectly.

## Action
- Corrected the build-tools expectation to Build-Tools.
- Added a plan-review assertion to confirm that a custom role containing a legacy role prefix is still presented as its own formatted name.
- Left production identity formatting, Host state mapping, model metadata and execution authority unchanged.

## Result
- Identity and state-presentation tests: 27 passed, zero failures, 44 assertions.
- TUI typecheck: exit 0.
- The historical phase-38 capitalization failure is resolved.
- Tests continue to distinguish reviewed planning from verified Ready and keep terminal failure states visible.

## Evidence
Bun 1.3.14 ran from runtime/packages/tui:
- bun test --timeout 10000 ./test/harness-identity-presentation.test.ts ./test/harness-status-presentation.test.ts
- bun run typecheck

The companion JSON records this gate. Earlier reports retain their historical failures rather than being rewritten as if those failures never happened.

## Residual Risk
- This is a two-file presentation gate, not the full TUI or repository suite.
- It introduces no new live-provider, packaging, cross-platform or visual-layout evidence.
- The separate Auth read-fixture TS2352 and Python disputed-history freshness fixture have their own successful correction reports.
- Real-account connectivity, broader regression coverage and startup variability remain outside this correction.
- Git and net_monitor.py were untouched; no commit or push occurred.
