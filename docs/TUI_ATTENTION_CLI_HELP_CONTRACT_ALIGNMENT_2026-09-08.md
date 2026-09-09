# TUI Attention and CLI Help Contract Alignment

## Situation

A fresh isolated run reproduced five previously reported failures: four TUI
attention assertions and one CLI help snapshot mismatch. Actual runtime output
used base-harness while the fixtures still expected opencode.

The help test also retained removed upstream commands and omitted execute.

## Reason

These failures did not demonstrate a broken notification renderer or help generator.
They were stale product contracts. Blind snapshot replacement alone would have
missed another weakness: a removed command can be interpreted as the default
TUI project positional and return top-level help with exit code zero.

## Action

- Updated default notification title and built-in sound-pack expectations to
  base-harness and base-harness.default.
- Preserved a separate explicit custom-title assertion.
- Aligned documented command coverage with the actual root help output.
- Added execute; removed upgrade, uninstall, github and pr from documented coverage.
- Removed the obsolete github subcommand cases.
- Asserted that the advertised root command list matches the independent expected list.
- Required each command response to begin with its own command heading and keep stdout empty.
- Regenerated help snapshots with Bun's snapshot command, then reran without updating.

No production runtime code was changed.

Changed artifacts:
- runtime/packages/base-harness/test/cli/cmd/tui/attention.test.ts
- runtime/packages/base-harness/test/cli/help/help-snapshots.test.ts
- runtime/packages/base-harness/test/cli/help/__snapshots__/help-snapshots.test.ts.snap

## Result

- Fresh baseline: 14 passed, 5 failed.
- Snapshot generation: 1 passed, 29 snapshots added, 94 assertions, 19.12 seconds.
- Clean regression: 19 passed, 0 failed, 29 snapshots, 158 assertions, 19.80 seconds.
- Host typecheck: exit code 0.
- TUI typecheck: exit code 0.
- No watchdog termination occurred.

## Evidence

Repository Bun 1.3.14 was used with isolated fixture homes.
Commands from runtime/packages/base-harness:

~~~text
bun test --timeout 30000 --only-failures --update-snapshots test/cli/help/help-snapshots.test.ts
bun test --timeout 30000 --only-failures test/cli/cmd/tui/attention.test.ts test/cli/help/help-snapshots.test.ts
bun run typecheck
~~~

TUI typecheck ran from runtime/packages/tui. Local diagnostic logs use:
.tools/validation/ui-help-contract-repair-1788871323420

Console messages about intentionally failed fake audio/notification operations
belong to negative test cases; the clean run reported zero failed tests.

## Residual Risk

- These checks do not prove Windows notifications actually appear or sound plays
  on a user's device; renderer and audio behavior use controlled test doubles.
- Help snapshots do not execute the commands' substantive workflows.
- Whole-product usability and full Host regression remain unverified after this change.
- Native symlink capability fixtures and the earlier shell timeout remain separate work.
- These are developer diagnostics, not Harness Evidence, Ready or independent user validation.
- No repository Git operations were performed. net_monitor.py was untouched.
