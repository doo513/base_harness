# Retired minimal runtime experiment

The prototype in `src/` is preserved for reference, not used by the product
entry point or workspace package graph. It bypassed KernelHost, Coordinator,
WorkGraph, scoped candidate verification, and the existing security policies.

The authoritative source launcher is `runtime/src/cli.ts`. It starts the
bundled Host. Do not reconnect this experiment as an alternate execution path.
