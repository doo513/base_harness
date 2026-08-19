# Phase 05 — Structured Tool Contracts

Status: IMPLEMENTED; targeted tests added; structured WRITE specialization remains deferred to domain/tool-gateway work.

## Problem / evidence

The Actor previously saw only tool description, side-effect, and idempotence. It had no machine-readable argument/result contract, while malformed arguments were often discovered only inside handlers. Development profiles also depended heavily on the generic shell for project inspection.

## Contract

- tools may declare bounded JSON input/output schemas;
- declared input schemas are checked before capability/permission/execution;
- declared output schemas are checked before a successful result is returned;
- sandbox command/argv/session tools expose default argument contracts;
- legacy `ToolSpec` without schemas remains backward compatible;
- schemas improve call correctness only and grant no capability or truth authority;
- structured workspace read tools must resolve every path through `WorkspaceContract` and stay bounded;
- no generic in-process WRITE tool is introduced because that would weaken Stage 02 strict-isolation behavior.

## Implementation

- extended tool specs with optional `input_schema` / `output_schema`;
- added a deterministic JSON-schema subset validator for object/array/string/number/integer/boolean/null, enum, required fields, additional-properties rejection, and basic bounds;
- added default schemas for sandbox shell/argv/session contracts;
- added pre-execution input and post-execution output validation to `ActionRuntime`;
- runtime context enriches model-visible tools with schemas only when declared, preserving Stage 07 legacy projection behavior;
- added bounded workspace READ tools: `file.read`, `directory.list`, and `file.search`;
- workspace read tools reject traversal/symlink escapes through `WorkspaceContract`.

## Structural review

- capability and permission checks remain in `ActionRuntime`;
- strict isolation still rejects generic in-process WRITE/EXTERNAL tools;
- schema validity cannot authorize an execution: it only rejects malformed values;
- tool output remains an untrusted observation until the normal verifier path promotes a claim;
- Stage 07 base `ContextProjector` is not rewritten; integration enrichment happens at the existing runtime context boundary.

## Validation focus

`tests/test_integration_tool_contracts.py` covers pre-handler input rejection, output mismatch rejection, shell argument schema, workspace traversal/symlink escape rejection, bounded read/search behavior, and model-visible sandbox schemas.

## Remaining limitations

- the schema validator intentionally implements a small subset, not full JSON Schema;
- structured file mutation/git/build/test tools are not added as in-process WRITE tools; domain integration must bind writes to the sandbox/tool gateway;
- MCP/plugin-provided schemas are validated/normalized in the next phase.
