# Integration Runtime Track

Status: ACTIVE on `develop`.

This track adds practical model/tool/workspace/domain integration around the frozen Verified-State Kernel. It does not create Stage 09 and does not relax Stage 00-08 guarantees.

## Why this track exists

The kernel already governs truth, completion, recovery, progress, context, retrieval admission, persistence, and tool isolation. The remaining gap is practical execution: selecting a workspace, resolving configuration and credentials, connecting real model providers, managing longer-horizon agent work, exposing structured tools/MCP/plugins, carrying useful context/memory across work, and completing Software/Hackathon domain behavior.

## Phase order

1. Workspace contract
2. Config and secret resolution
3. Model Gateway
4. Agent control state
5. Structured tool contracts
6. MCP/plugin gateway
7. Context relevance
8. Cross-run project/episodic memory
9. Software/Hackathon domain completion
10. Progress/recovery alignment
11. Real E2E and benchmark/ablation
12. TUI

## Phase gate

Each phase must record:

- problem/evidence motivating the change;
- contract and non-goals;
- files and behavior changed;
- targeted validation;
- full regression/prior-Stage validation status;
- structural/security review;
- unresolved limitations and follow-up.

A phase is not a prerequisite for the next phase until these checks pass. Model/tool/retrieval/plugin output never gains trusted-state or completion authority directly.

## Baseline

- branch: `develop`
- pre-integration frozen branch: `preprocessing`
- starting implementation commit: `75834ac1ecb6c022771c2efee1f19495f356ee76`
- package line: `0.9.1`
- Stage 00-08: frozen, except confirmed defect fixes

The first prerequisite correction is CI/document consistency because the inherited workflows and handoff documents still referenced deleted historical branches and pre-Stage08 status.
