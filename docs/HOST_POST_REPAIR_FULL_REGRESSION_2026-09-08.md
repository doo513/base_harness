# Host full regression after targeted repairs

## Situation

Targeted checks for ACP, TUI attention, CLI help, shell, and native symlink reporting had completed. A new full Host run was necessary because isolated passes do not establish full-suite or real-user stability.

## Reason

The previous full run had 16 failing tests and one additional error. Native capability skips must remain separate from passed checks. Timing failures must not be declared resolved solely because a fresh process passes in isolation.

## Action

- Ran the complete Host suite with bundled Bun 1.3.14, the existing 30000 ms default test timeout, no early bail, and no snapshot update mode.
- Used the existing isolated test environment, disabled model catalog fetching, and selected the bundled Python verifier.
- Continued observing the same live process until it terminated. Quiet output did not trigger a restart.
- Made no source changes during the full run.
- Inspected the remaining failure paths using cached test and CLI sources and the Truncate and Config modules.
- Did not perform repository Git operations or touch net_monitor.py.

## Result

| Metric | Previous full run | Current full run |
| --- | --- | --- |
| Passed | 3247 | 3260 |
| Skipped | 55 | 60 |
| Todo | 1 | 1 |
| Failed | 16 | 3 |
| Additional errors | 1 | 1 |
| Reported tests | 3319 | 3324 |
| Files | 250 | 250 |
| Assertions | 8648 | 8779 |
| Exit code | 1 | 1 |
| Duration, seconds | 6707.43 | 1929.75 |

The current run reported 45 snapshots with no snapshot failure. It is still a failed full regression, not a promotion pass. Five previously failing native symlink cases are now explicitly skipped because capability probes returned EPERM; these are not five fixed or validated native behaviors. The duration difference is diagnostic only and is not a controlled performance benchmark.

## Evidence

These results are developer diagnostics, not Harness Evidence, Ready artifacts, or independent user validation.

Command from runtime/packages/base-harness:

```text
.tools/bun-1.3.14/bun.exe test --timeout 30000 --only-failures
```

The executable was invoked by its absolute repository path. Environment overrides included BASE_HARNESS_DISABLE_MODELS_FETCH=true, BASE_HARNESS_REQUIRE_SYMLINK_TESTS=0, and BASE_HARNESS_PYTHON pointing to the bundled verifier Python.

- Raw log: .tools/validation/host-full-post-repair-1788872042170.log.
- Process session 58527 terminated with exit code 1; it must not be polled or restarted as an unfinished run.
- Truncate fresh-process loading exceeded its unchanged 20000 ms test limit at 20001.73 ms. A subsequent ProcessRunFailedError was also reported with empty stdout and stderr.
- ACP model-option listing failed with an Effect TimeoutError; total reported case duration was 17175.71 ms. The client uses a 15-second response wait, but the output does not establish which startup or request phase stalled.
- ACP stdin EOF termination exceeded its unchanged 5-second operation timeout; total reported case duration was 5173.69 ms.
- No other failing test was reported in this full run.

## Residual Risk

- The three subprocess timing failures reproduce in the full suite despite earlier isolated passes. Startup cost, parent resource pressure, test order, and cleanup interactions are hypotheses, not established causes.
- Existing ACP fixture code captures child stderr but timeout errors do not include it or identify the outstanding request phase. Existing startup trace events can help distinguish module loading from provider initialization without exposing credential contents.
- Truncate imports the Config implementation to access its service identity; Config imports account, authentication, package installation, and other configuration dependencies. This is observable import coupling, not proof that it caused the timeout.
- Next investigation should retain the current deadlines and report child process state and bounded structured startup stages on failure before selecting a runtime optimization.
- Native Windows symlink validation remains unavailable on this host.
- Full Core regression after test-environment isolation remains pending.
- Real TUI use, OAuth/provider connections, and independent user acceptance remain unproven.
