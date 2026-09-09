# Full Host regression after ACP EOF and Config boundary repairs

## Situation

The preceding complete Host run had three failures: Truncate fresh-process loading, ACP initialization, and ACP empty-input termination. The Config service contract was separated from implementation loading and ACP received an input gate before AppRuntime initialization.

## Reason

Targeted passes were insufficient to establish that the failures were resolved in the full suite. The existing operation deadlines and native capability reporting had to remain intact.

## Action

- Ran the complete Host suite with Bun 1.3.14, the existing default test timeout, no early bail, and no snapshot update mode.
- Observed the original live session until termination without restarting it for quiet output.
- Made no source changes while the suite was running.
- Used the newly added bounded ACP startup diagnostics to identify the remaining failing phase.
- Inspected CLI command dependency boundaries after the run. No further source changes have been applied from that inspection.
- Performed no repository Git operations and did not touch net_monitor.py.

## Result

| Metric | Result |
| --- | --- |
| Passed | 3273 |
| Skipped | 60 |
| Todo | 1 |
| Failed | 1 |
| Additional errors | 0 |
| Reported tests | 3335 |
| Files | 252 |
| Snapshots | 45, no reported failure |
| Assertions | 8834 |
| Duration | 1902.97 seconds |
| Exit code | 1 |

Truncate fresh-process loading and ACP empty-input termination passed in this full run. ACP initialization is the sole remaining reported failure. The run remains a failed promotion gate, not a successful release validation.

## Evidence

Developer diagnostics only; not Harness Evidence, Ready artifacts, or independent user validation.

- Full-run session 13960 is terminal with exit code 1 and must not be polled as an unfinished run.
- Failing case: test/cli/acp/config-options.test.ts, model option is listed with category model.
- Actual failing operation: request:initialize, before session creation or model-option retrieval.
- Reported case duration: 17176.51 ms, including failure cleanup.
- At the 15-second response deadline, child PID 34944 remained running with zero stdout protocol lines.

```json
{
  "elapsedMs": 15015,
  "exitCode": null,
  "stdoutLines": 0,
  "startup": [
    { "stage": "cli.modules_ready", "processUptimeMs": 9093 },
    { "stage": "cli.parse_start", "processUptimeMs": 9109 },
    { "stage": "cli.options_ready", "processUptimeMs": 9339 },
    { "stage": "cli.input_wait", "processUptimeMs": 9369 },
    { "stage": "cli.input_ready", "processUptimeMs": 9378 },
    { "stage": "runtime.import_start", "processUptimeMs": 9378 }
  ]
}
```

No runtime.import_ready or runtime.services_start event had been observed at the timeout. This locates the failure before protocol initialization completes; it does not establish a model-provider response failure or a GoalContract verification failure.

## Residual Risk

- CLI initial module loading consumed approximately nine seconds in this observed child. AppRuntime import had not completed within the remaining response window. Individual module costs, resource pressure, and cold-load effects are not yet isolated.
- The CLI entry point eagerly imports multiple command modules. Provider credential management imports Plugin and the Config implementation; MCP management imports MCP, OAuth, and debug transport implementations. These are candidate dependency boundaries, not proven sole causes.
- The serve and web command modules already defer their Server import and should not be blindly rewritten as if they eagerly loaded it.
- Next work should preserve argument parsing and help contracts while reducing eager runtime imports, then rerun the unchanged initialization deadline.
- The 60 skipped tests, including unavailable native Windows symlink checks, remain outside the passing coverage.
- Core's post-isolation full regression passed separately, but independent user stability, real OAuth/provider use, and broader deployment validation remain incomplete.
