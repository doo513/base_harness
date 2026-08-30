# Strict Execution Isolation

## Situation

Worker file edits used Overlay boundaries, but root shell execution still inherited the Host filesystem, process tree, environment, and network.

## Reason

Verification could be correct while an execution step still affected unrelated Host state or leaked credentials.

## Action

Strict shell actions now use WSL2 on Windows or Linux namespaces directly, copy a validated workspace, enter user/mount/pid/network namespaces and a chroot, expose only loopback networking, sanitize the environment, and enforce process, memory, output, input, and time limits. Adaptive Windows processes receive best-effort Job Object containment.

## Result

Strict execution is fail-closed when the backend is unavailable, sandbox failures are recorded as Harness failures, and model-provider networking remains outside the tool sandbox.

## Evidence

Sandbox policy, escape, WSL2 execution, network, read-only system, workspace isolation, timeout, process cleanup, configuration, SDK, and typecheck results form the promotion evidence for this phase.
