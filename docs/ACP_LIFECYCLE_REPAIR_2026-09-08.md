# ACP Lifecycle Repair

## Situation

The full Host regression reported 16 failed tests and one additional error.
A fresh, isolated four-case run reproduced ACP stdin EOF timeout and the
embedded prompt-content session failure. Model option discovery and fresh
truncate-process startup passed in that run.

## Reason

The ACP command eagerly initialized a project instance even though ACP sessions
load their directories through the Host API. It also installed its completion
listener after asynchronous connection setup, permitting an EOF observation race.
The command did not explicitly release its listener and event subscription.
These are concrete lifecycle defects; this investigation does not attribute
every earlier timeout to them.

## Action

- Set the ACP command to instance-free startup.
- Resolve input completion from the stream EOF handler rather than a later listener.
- Handle input errors through the same completion promise.
- Add explicit disposal of ACP event subscriptions.
- Acquire and release the local server around the connection lifetime.
- Preserve the existing five-second EOF assertion and all verification policies.

Changed runtime files:

- runtime/packages/base-harness/src/cli/cmd/acp.ts
- runtime/packages/base-harness/src/acp/agent.ts

## Result

- Fresh four-case reproduction before changes: 2 passed, 2 failed.
- Same four cases after changes: 3 passed, 1 failed, 15 assertions, 26.50 seconds.
- ACP lifecycle and config-option regression: 10 passed, 0 failed,
  67 assertions, 69.50 seconds.
- Host typecheck: exit code 0.
- The EOF test now passes with its original five-second limit.
- Embedded resource prompt content still fails with RPC code -32603 and
  service=session. Its underlying cause is not established.

## Evidence

Validation used the repository Bun 1.3.14 binary, isolated fixture homes,
and scripted local model responses. No paid provider calls were made.
Both validation commands completed without watchdog termination.

Commands, from runtime/packages/base-harness:

```text
bun test --timeout 30000 --only-failures --test-name-pattern "loads truncate effect in a fresh process|stdin EOF exits cleanly|model option is listed with category|accepts embedded text resource image and file resource link prompt content" test/tool/truncation.test.ts test/cli/acp/config-options.test.ts test/cli/acp/lifecycle.test.ts test/cli/acp/prompt-content.test.ts
bun run typecheck
bun test --timeout 30000 --only-failures test/cli/acp/lifecycle.test.ts test/cli/acp/config-options.test.ts
```

These are developer diagnostic results, not Harness Evidence or Ready artifacts.
They are not independent user validation.

## Residual Risk

- The embedded prompt-content failure remains unresolved.
- Full Host regression has not been rerun after this repair; the earlier failed
  full-run result remains authoritative for that run.
- These fixtures do not establish real OAuth/provider reliability, practical
  task completion quality, or independent real-user stability.
- Clean EOF and lifecycle fixtures do not prove cancellation of every active
  worker, MCP subprocess, or platform-specific execution tree.
- No repository Git operations were performed. net_monitor.py was untouched.
