# Deferred Location Runtime Loading

## Situation
The latest complete Host suite had 3275 passes, 60 skips, 1 todo and one failure: the first ACP initialize response exceeded its existing 15-second deadline. Startup diagnostics placed the wait inside AppRuntime module loading, not model invocation. Isolated initialization succeeded.

## Reason
Core AppNodeBuilder statically imported location-services before checking whether the graph required LocationServiceMap. That module imports tools, provider integration, plugins, filesystem services and session execution. A conditional service check therefore did not create a conditional module-loading boundary.

## Action
- Replaced the static location-services import with Effect.promise plus Layer.unwrap inside the existing required-service branch.
- Kept the synchronous graph-building API, replacement handling and LayerNode.compile behavior.
- Preserved location service construction when acquired; did not remove services.
- Kept ACP deadlines, verification policy, provider behavior and Ready rules unchanged.
- Did not change user settings, credentials, net_monitor.py or Git state through Git commands.

## Result
- Core typecheck: exit 0.
- Existing node-build tests: 4 passed, 0 failed, 8 assertions, 2.78 seconds.
- Host typecheck: exit 0.
- ACP diagnostic, input, config-option, lifecycle and prompt-content tests: 23 passed, 0 failed, 154 assertions, 92.68 seconds.
- Isolated real CLI ACP initialization succeeded, made zero model calls and stopped its child process.
- No complete Host rerun was performed in this change.

## Evidence
Developer diagnostics only; these results are not Harness Evidence or independent user validation.
The existing node-build tests exercise a graph without location services, replacement cycle detection, shared project acquisition and normal graph composition.
The ACP probe recorded runtime.import_start at 673 ms and runtime.import_ready at 3975 ms of process uptime. This single sample is not a controlled performance comparison.
The previous complete-suite failure remains unresolved at the full-suite level until reproduced and retested there.
Machine-readable results: LOCATION_RUNTIME_LAZY_LOADING_DIAGNOSTICS_2026-09-09.json.

## Residual Risk
- Cache state, machine load and other dependency paths may still affect startup.
- Deferred module acquisition uses asynchronous Effect execution; this change does not establish synchronous acquisition guarantees.
- Windows symlink capability skips remain unvalidated on this machine.
- Real OAuth/provider sessions, independent user acceptance and long-running practical stability were not established.
- No paid model calls, commit or push were performed.

