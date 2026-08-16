# Verified-State Harness — Current Agent Handoff

The inherited handoff explicitly stated **Stage 02 PARTIAL / NOT EXITED**. That historical state is preserved in `handoff/prompts/GENERAL_CONTINUATION_PROMPT_INHERITED_STAGE02.md` and the artifact index. The agent producing this branch therefore did not skip ahead: its first task was **Production Sandbox Backend + actual filesystem/network attack probe**.

## Current status

```text
Stage 00  COMPLETE
Stage 01  COMPLETE for scoped P0 defects
Stage 02  PASS / EXITED after rc2 direct runtime evidence
Stage 03  NEXT / NOT STARTED
```

Stage 02 final evidence:

```text
12/12 required attacks PASS
4/4 defense-in-depth attacks PASS
47 pytest tests PASS
compileall PASS
runtime attestation source = runtime_probe
```

The PASS is conditional on `LinuxNamespaceSandboxBackend` live attestation succeeding on the execution host. The local subprocess backend still does not count as a sandbox.

## Project objective

Build a **General Harness Kernel + Domain Profile** architecture whose central invariant is:

> Actor output may propose and act, but only sufficiently strong harness-side verification/oracles may promote trusted truth or completion.

## Mandatory workflow

```text
Inspect → Reproduce current evidence → Freeze active stage contract
→ Implement active stage only → Unit/integration/adversarial tests
→ Full regression → Logic/security re-review → Freeze raw evidence
→ Detailed stage report → PASS/PARTIAL/FAIL → Continue only on PASS
```

## Read order

1. `00_PROJECT_CONTEXT.md`
2. `01_ARCHITECTURE.md`
3. `02_CURRENT_STATUS.md`
4. `03_NEXT_STAGE_TASK.md`
5. `04_EXECUTION_PROTOCOL.md`
6. `05_VALIDATION_GATES.md`
7. `06_EVIDENCE_STANDARD.md`
8. `15_DO_NOT_DO.md`
9. Stage 02 rc2 reports/evidence

Then inspect code; documentation is not a substitute for runtime verification.
