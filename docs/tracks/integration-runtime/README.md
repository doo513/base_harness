# Integration Runtime Track

Status: **IMPLEMENTED / VALIDATED** on `develop`; promotion to `main` follows the final documentation CI gate.

This track adds practical model/tool/workspace/domain integration around the frozen Verified-State Kernel. It does not create Stage 09 and does not relax Stage 00-08 guarantees.

## Implemented runtime surface

```text
workspace contract
-> config / env-backed secrets
-> Model Gateway
-> Agent Control
-> structured tool contracts
-> MCP stdio / explicit plugins
-> context relevance
-> cross-run project memory
-> Software / Hackathon / CTF profiles
-> progress / recovery alignment
-> E2E + evaluation infrastructure
-> CLI
-> TUI
```

The TUI is a thin launcher/monitor over the existing CLI and Kernel. It does not create a second execution or verification authority.

## Phase history

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
11. Real E2E
12. Benchmark/ablation infrastructure
13. TUI

## Validation gate

The post-implementation audit changed the validation rule from “tests/docs exist” to executable evidence:

```text
editable install
-> compile
-> CLI/TUI module + installed entrypoint smoke
-> full pytest
-> core freeze audit
-> Stage 03-08 regression/adversarial/cost probes
-> Stage 02 isolation/binding regression probes
```

The validated source commit recorded:

```text
harness/full-regression = success
268 passed, 7 skipped
all listed probe gates = PASS
```

See:

- `CI_STATUS.md` for the persisted gate ledger;
- `POST_IMPLEMENTATION_AUDIT.md` for defects found, fixes, remaining capability gaps, and the promotion decision;
- `IMPLEMENTATION_REPORT.md` and `PHASE*.md` for implementation rationale/history.

## Remaining work is evidence-driven

The integration track is no longer blocked on basic runtime plumbing. Follow-up work should be driven by real runs and benchmarks rather than adding breadth speculatively. Current known gaps include interactive persisted MCP approval, stronger Windows isolation, broader native providers/MCP transport, plugin isolation, semantic context ranking, richer memory lifecycle, domain-depth expansion, progress tuning, and repeated matched real-provider performance evaluation.

The active cross-run lifecycle extension is specified in `EVIDENCE_MEMORY_LIFECYCLE_V2.md`; it preserves the Stage-08 untrusted retrieval boundary and remains pending validation evidence.

## Branch baseline

- implementation branch: `develop`
- user-facing promotion branch: `main`
- archived former main: `legacy-main-pre-integration`
- frozen pre-integration snapshot: `preprocessing`
- starting integration commit: `75834ac1ecb6c022771c2efee1f19495f356ee76`
- package line: `0.9.1`
- Stage 00-08: frozen except confirmed defect fixes

Model/tool/retrieval/plugin output never gains trusted-state or completion authority directly.
