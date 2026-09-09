# Lazy CLI command registration

## Situation

The last full Host run had one remaining failure: the first ACP initialize request timed out before AppRuntime import completed. Its startup trace showed approximately nine seconds spent before CLI modules were ready. The CLI entry point still eagerly imported unrelated command implementations.

## Reason

The existing lazyCommand adapter and the installed yargs implementation already support asynchronous named-command builders. Reusing that mechanism avoids a new parser or duplicated option definitions. Shared command identities prevent registration metadata from drifting from implementation metadata.

## Action

- Converted 13 remaining named commands to the existing lazy registration path: console, agent, models, stats, export, import, session, plugin, db, serve, web, providers, and mcp.
- Moved their command names, descriptions, and aliases into EntryCommand and reused those identities in the implementations.
- Preserved the actual builders, handlers, nested subcommands, registration order, aliases, hidden status, and root TUI synchronous builder.
- Retained lazyCommand identity and unsupported-middleware guards without relaxing them.
- Kept the small hidden generate command unchanged; its implementation imports were already deferred.
- Added two registration-boundary tests for eager command imports, deferred named commands, identity uniqueness, aliases, and hidden console status.
- Recovered an initial patch-context failure by ordering patch hunks according to the unchanged index file. No user changes were overwritten.
- Ran the complete CLI test directory and Host typecheck without updating snapshots or increasing timeouts.
- Did not change model reasoning mappings, authentication behavior, verification policy, net_monitor.py, or repository Git state.

## Result

| Check | Result |
| --- | --- |
| Host typecheck | Exit 0 |
| Complete CLI test directory | 173 passed, 1 skipped, 0 failed |
| Help snapshots | 29 passed without update mode |
| Assertions | 741 |
| Reported cases and files | 174 cases across 31 files |
| CLI suite duration | 215.91 seconds |
| Validation processes | Terminated normally; no watchdog timeout |

ACP, command argument handling, help output, and CLI-side TUI tests passed in this run. Full Host validation remains pending after this change.

## Evidence

Developer diagnostics only; not Harness Evidence, Ready artifacts, or independent user validation.

- Runtime: bundled Bun 1.3.14 on Windows.
- Validation session 53732 exited with code 0.
- Commands: bun run typecheck and bun test --timeout 30000 --only-failures test/cli.
- The new boundary test uses Bun's import scanner rather than substring matching to identify eager command implementation imports.
- Existing CLI help snapshots remain unchanged, preserving visible names, aliases, descriptions, options, and nested help behavior covered by those fixtures.
- Native Zed symlink coverage remains explicitly skipped on this host because the capability probe returned EPERM.

## Residual Risk

- A full Host rerun is still needed to establish whether the original full-suite initialize timeout is resolved. Passing the isolated CLI suite is not enough.
- AppRuntime still loads its service graph for real requests. This change removes unrelated command implementation loading, not all initialization work.
- No controlled startup benchmark or real-user latency guarantee is claimed.
- Snapshot and fixture passes do not validate real OAuth accounts, provider availability, long-running TUI use, or independent user acceptance.
- Windows native symlink validation remains unavailable in the current environment.
