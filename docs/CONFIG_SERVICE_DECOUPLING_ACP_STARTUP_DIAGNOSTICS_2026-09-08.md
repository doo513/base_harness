# Config service decoupling and ACP startup diagnostics

## Situation

The latest complete Host regression still had three subprocess timing failures. Isolated passing runs had not explained why ACP startup and Truncate loading failed in the complete suite.

## Reason

Truncate depended on the full configuration implementation merely to obtain its optional service. The configuration implementation imports account, authentication, and package-installation functionality. ACP timeout errors did not expose the startup phase, preventing a useful distinction between module loading, service initialization, and protocol response delays.

## Action

- Extracted the Config service identity and interface into src/config/service.ts. The existing Config module re-exports the same Service class, preserving service identity and configured behavior.
- Changed Truncate to depend on the service contract instead of the configuration implementation.
- Added bounded ACP fixture diagnostics containing PID, elapsed time, exit state, stdout line count, and allowlisted startup stages with timing.
- Bounded the subprocess stderr diagnostic tail to 8192 characters. Only projected structured startup fields enter ACP timeout errors; raw stderr and arbitrary trace payload fields are excluded.
- Enabled existing startup tracing for ACP fixtures and added operation labels to response and EOF timeout errors.
- Kept the existing 15-second response and 5-second EOF deadlines. Response and notification deadlines now cover the entire wait rather than restarting for each unrelated message.
- Added four deterministic diagnostic projection and bounding tests.
- Did not change provider authentication, verification policy, stored artifacts, OS permissions, or net_monitor.py. No Git operations were performed.

## Result

| Check | Result |
| --- | --- |
| Host typecheck | Exit 0 |
| Config, Truncate, diagnostic, and ACP targeted group | 130 passed, 1 failed, 321 assertions, 6 files, 125.79 seconds |
| Remaining targeted failure | ACP stdin EOF exits cleanly |
| Validation process cleanup | All child processes stopped; no watchdog timeout |

The Truncate fresh-process case and ACP model-option cases passed in this targeted group. This does not prove their full-suite timing failures are resolved.

## Evidence

Developer diagnostics only; not Harness Evidence, Ready artifacts, or independent user validation.

The remaining EOF timeout reported:

```json
{
  "pid": 33232,
  "elapsedMs": 5022,
  "exitCode": null,
  "stdoutLines": 0,
  "startup": [
    { "stage": "cli.modules_ready", "processUptimeMs": 2523 },
    { "stage": "cli.parse_start", "processUptimeMs": 2537 },
    { "stage": "cli.options_ready", "processUptimeMs": 2656 },
    { "stage": "runtime.import_start", "processUptimeMs": 2675 },
    { "stage": "runtime.import_ready", "processUptimeMs": 3615 },
    { "stage": "runtime.services_start", "processUptimeMs": 3615 },
    { "stage": "provider.services_start", "processUptimeMs": 3794 },
    { "stage": "provider.services_ready", "processUptimeMs": 3794 },
    { "stage": "provider.services_start", "processUptimeMs": 4602 },
    { "stage": "provider.services_ready", "processUptimeMs": 4602 }
  ]
}
```

The fixture closes stdin immediately after spawning. These observations establish that this EOF-only invocation initializes runtime and provider services before terminating. They do not prove which individual initializer dominates every failing run.

## Residual Risk

- ACP EOF handling must move ahead of unnecessary service initialization. The next change must preserve buffered nonempty protocol input and normal cleanup after real work.
- The complete Host suite has not been rerun after this change. Its last complete result remains a failure.
- Config contract extraction is a dependency-boundary improvement, not a measured proof of startup speed or the sole timeout cause.
- Diagnostic projection is tested, but a dedicated regression for unrelated notifications not extending a request deadline remains desirable.
- Native Windows symlink checks and independent real-user stability remain unvalidated. Full Core regression after environment isolation is still pending.
