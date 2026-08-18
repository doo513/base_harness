# Phase 01 — Workspace Contract

Status: IMPLEMENTED; CI configured on `develop`; connector-level static/structural re-review complete.

## Problem / evidence

Before this phase the runtime used `Path(workspace).resolve()` while domain profiles independently constructed tools from their own `profile.workspace`. A caller could therefore select one runtime workspace while a profile tool executed in another directory. There was also no explicit contract for optional temp/build/cache locations.

## Contract

- the user-selected directory is the actor workspace root;
- the root must already exist and be a directory;
- optional temp/build/cache directories must remain inside the root;
- actor-relative path resolution must not escape the root;
- every tool declaring an execution workspace must execute at the root or a descendant;
- workspace topology is not claimed to be OS sandboxing;
- Stage 02 `SecurityLayout` and execution-backend isolation remain authoritative for stronger boundaries.

## Implementation

- added `harness.core.workspace.WorkspaceContract`;
- added fail-closed `WorkspaceContractError`;
- bound `HarnessRuntime.workspace` to the contract root;
- validate profile tool execution workspaces before constructing `ActionRuntime`;
- include the workspace contract in semantic config/resume provenance and run events;
- added focused tests for root selection, managed dirs, traversal rejection, profile/runtime workspace mismatch, and config provenance.

## Structural review

- no verified-state commit authority changed;
- no verifier/oracle/recovery/progress/context/retrieval authority changed;
- no actor tool gained access outside its previously declared backend; the change only rejects inconsistent execution workspaces earlier;
- legacy callers using the same profile/runtime workspace remain compatible;
- intentionally stricter behavior: nonexistent workspace roots and profile/runtime workspace mismatches now fail before execution.

## Validation

Repository CI now runs full pytest and Stage 02-08 probes on `develop`, plus the live persistent-session namespace probe in the generic runtime-isolation workflow. New targeted tests live in `tests/test_integration_workspace.py`.

The current connector exposes commit status contexts but not push-triggered Actions run enumeration, so the implementation evidence records that CI is wired and the source/test contracts were statically re-reviewed here; promotion to `main` still requires observable successful CI evidence.

## Remaining limitations

- config files do not yet populate temp/build/cache settings; Phase 02 owns that;
- workspace does not perform repository discovery or semantic project understanding;
- workspace contract is a topology contract, not a substitute for Linux namespace or another strong sandbox.
