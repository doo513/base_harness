# CLI Help Repair: Partial Result (2026-09-08)

## Situation
The lazy default command introduced blank root help, one failing test and eight Host type diagnostics. The user explicitly approved a repair.

## Reason
Yargs root help does not await an asynchronous default builder. Awaiting parseAsync does not cover detached help rendering. An exploratory getHelp call also printed named-command help before returning it, so it was not adopted.

## Action
- Extracted the unchanged TUI option builder into src/cli/tui-options.ts and shared it with the entrypoint and original TUI command.
- Kept this default builder synchronous, while the handler and named command modules remain lazy.
- Added a loaded-builder identity check to prevent execution with a different option contract.
- Corrected async-builder cast and test callback annotations.
- Ran targeted tests, Host typecheck and isolated actual CLI help/handler diagnostics using Bun 1.3.14.
- The first patch failed on an incomplete-line test anchor; recovery confirmed all original files remained unchanged before applying the intended patch.

## Result
**Partial repair, not promotion-ready.**
- Tests: 16 passed, 0 failed, 38 assertions.
- Actual root --help and -h: exit 0, 4161 stderr bytes, command listing and --mini present.
- Actual --help=true: exit 0, 3823 stdout bytes, command listing and --mini present. Its existing stdout rendering route differs from the exact --help/-h route.
- Actual run/execute/attach help: exit 0, nonempty output, relevant original options present.
- Actual --mini --replay: original handler rejected the unsupported option, exit 1, without builder mismatch.
- Zero inference requests. All diagnostic processes terminated.
- The original eight diagnostics no longer appeared, but four TS2322 diagnostics now reject concrete command handler types at the lazy registration boundary. Full Host typecheck still fails.

## Evidence
See the companion JSON for process outcomes and output sizes. These are local engineering diagnostics, not Harness Evidence, Ready, independent user validation or a real-model usability evaluation.

## Residual Risk
The new AnyCommand intersection widened the middleware shape at the loader boundary and exposed concrete-handler assignability failures. A follow-up should keep the original CommandModule loader type and narrow the optional runtime middleware inspection locally, rather than weakening every handler contract. That correction has not been applied; user approval is required for this newly discovered issue.
No speedup or general stability claim is made. Earlier pending failures were not repaired. Git and net_monitor.py were not touched.
