# CLI Lazy Loading Type Boundary Repair (2026-09-08)

## Situation
The previous help repair restored actual CLI output, but the Host typecheck reported four TS2322 errors at lazy command registrations. The user approved continuing the repair.

## Reason
Extending the entire CommandModule loader contract with an optional middleware shape caused concrete handler argument types to fail assignment. Runtime inspection needed that optional field; the whole loader contract did not.

## Action
- Restored AnyCommand to CommandModule<any, any>.
- Applied the optional middleware shape only to the local middleware inspection.
- Preserved middleware rejection, builder identity checking, synchronous default options and lazy handlers.
- Ran the same targeted tests and Host typecheck with Bun 1.3.14.

## Result
- Targeted tests: **16 passed, 0 failed**, 38 assertions.
- Host typecheck: **exit 0**, no diagnostics.
- Combined validation process: **exit 0**.
- The requested four type errors are resolved. No new source changes were made after validation.

## Evidence
The companion JSON records the commands, scope and outcomes.
The expected CLI_COMMAND_BUILDER_MISMATCH stack printed during the negative test is not a test failure; the rejection assertion passed.
Actual CLI help was exercised in the previous report, not rerun here. This turn's evidence is limited to the targeted tests and Host typecheck.

## Residual Risk
This repair does not establish full product stability, real-provider usability or startup speed improvement. Earlier unrelated pending failures remain outside scope. No Git operations or net_monitor.py changes were made.
