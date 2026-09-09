# Runtime import phase diagnosis

## Situation

The full Host rerun after lazy CLI registration still failed the first ACP initialize request. The CLI front-end phase became shorter in the observed trace, but AppRuntime import remained incomplete at the existing 15-second response deadline.

## Reason

The previous trace could not distinguish loading the runtime's static dependencies from constructing its service graph. Changing the graph algorithm or removing services without that distinction would be speculative and could compromise existing behavior.

## Action

- Observed full Host session 25108 to termination without restarting it or changing code during the run.
- Inspected AppRuntime, its builder adapter, the Core app-node builder, and the LLM module dependency declarations.
- Added three diagnostic-only stages: runtime.modules_ready, runtime.layer_ready, and runtime.managed_ready.
- Kept service membership, lifecycle, provider behavior, verification policy, and timeouts unchanged.
- Ran a real isolated ACP initialization probe with temporary application state, a local dummy provider endpoint, model catalog fetching disabled, and no model prompt.
- Ran Host typecheck and the ACP/input/diagnostic targeted group after adding the stages.
- Did not perform Git operations, modify user credentials, or touch net_monitor.py.

## Result

| Check | Result |
| --- | --- |
| Full Host suite before the new phase markers | 3275 passed, 60 skipped, 1 todo, 1 failed, exit 1 |
| Full Host scope | 3337 cases, 253 files, 45 snapshots, 8858 assertions |
| Full Host duration | 1933.48 seconds |
| Isolated ACP initialization probe | Initialized successfully; zero model calls; child stopped |
| Host typecheck after markers | Exit 0 |
| Targeted checks after markers | 23 passed, 0 failed, 154 assertions, 5 files, 104.99 seconds |

The full initialization failure is not resolved. The probe and targeted passes cannot replace the failed full-suite result.

## Evidence

Developer diagnostics only; not Harness Evidence, Ready artifacts, or independent user validation.

The failing full-suite child reported CLI modules ready at 907 ms and AppRuntime import starting at 1134 ms. At 15053 ms it was still running, had produced zero protocol response lines, and had not reported runtime.import_ready. The failed test's total duration, including cleanup, was 17207.31 ms.

The isolated probe reported:

| Stage | Process uptime, ms |
| --- | ---: |
| cli.modules_ready | 749 |
| cli.input_ready | 989 |
| runtime.import_start | 990 |
| runtime.modules_ready | 5367 |
| runtime.layer_ready | 5369 |
| runtime.managed_ready | 5370 |
| runtime.import_ready | 5370 |
| runtime.services_start | 5370 |

In that probe, dependency/module evaluation took approximately 4377 ms after import started, whereas layer construction took approximately 2 ms. These are phase measurements from one isolated invocation, not a controlled benchmark or a guarantee under full-suite load.

AppRuntime statically imports dozens of service modules, including provider, LLM, tool, session, LSP, MCP, and workspace functionality. The Core builder only constructs a location service map when an unbound dependency requires it; the measured layer phase does not support blaming that graph calculation for the observed multi-second delay.

## Residual Risk

- The full-suite environment slows runtime import beyond the isolated probe. Resource pressure, cold dependency loading, and inherited test context require a focused reproduction before another speculative runtime change.
- Lazy CLI registration reduced the front-end phase in the observed full trace, but did not resolve the overall startup deadline.
- The new phase markers have passed targeted checks, not a further full Host run.
- Skipped checks, including Windows native symlink cases, remain unvalidated.
- Real provider authentication, long-running TUI use, independent user acceptance, and deployment stability remain incomplete.
