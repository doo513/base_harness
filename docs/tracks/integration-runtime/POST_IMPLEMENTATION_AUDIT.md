# Post-Integration Functional Audit

Date: 2026-08-19
Scope: integrated runtime on `develop`, before promotion to `main`.

## Audit rule

A feature is counted as implemented only when its executable source exists and the public entrypoint can be exercised by CI. Documentation or tests alone are not implementation evidence.

## Immediate-use findings

| Finding | Severity | Status | Action |
|---|---:|---|---|
| `PHASE13_TUI.md` and TUI tests existed while `src/harness/tui.py` was absent | High | FIXED | implemented `harness.tui` |
| no installed TUI console entrypoint | Medium | FIXED | added `verified-harness-tui` |
| CI did not explicitly smoke CLI/TUI entrypoints | High process defect | FIXED | added module + console-script smoke gate |
| regression CI only targeted `develop` | Medium | FIXED | CI now targets `develop` and `main` |
| CI result was not observable through the current connector | High process defect | FIXED | publishes `harness/full-regression` commit status |
| README did not provide end-user setup / model API / TUI / CLI instructions | Medium | FIXED | README operational guide added before promotion |

## Runtime surface review

```text
Workspace Contract          present
Config / env SecretRef      present
Model Gateway               present
  command provider          present
  OpenAI-compatible HTTP    present
Agent Control               present
Tool Contracts              present
Workspace read tools        present
Shell/argv write path       present through Tool Runtime
MCP stdio gateway           present
Plugin gateway              present
Context governance          present
Context relevance           present (lexical)
Project memory              present (opt-in)
Software profile            present
Hackathon profile           present
Progress control            present
Recovery                    present
Verification/oracles        present
Resume/persistence          present
Evaluation/ablation         present
CLI                         present
TUI                         present after this audit
```

## Remaining functional limitations

These do not block basic Software/Hackathon runs through CLI/TUI, but they are real capability gaps and must not be described as implemented.

1. **Interactive MCP approval** — MCP tools default to confirmation, but no persisted Kernel-owned approval request/response UI exists yet. TUI cannot interactively approve those calls.
2. **Strong Windows execution isolation** — the strong namespace backend is Linux-specific. `local` execution is usable for local development but is not a strong sandbox boundary.
3. **Provider breadth / streaming** — native Anthropic/Gemini adapters and harness-level streaming are absent. Gemini is usable through its OpenAI-compatible endpoint.
4. **MCP breadth** — v1 supports stdio tool discovery/calls, not HTTP transport, resources, prompts, sampling, elicitation, or tasks.
5. **Plugin isolation** — installed Python plugins are trusted host extensions; strict isolation rejects this path.
6. **Context ranking** — active-context relevance is deterministic lexical ranking, not semantic/embedding ranking.
7. **Memory lifecycle** — no decay/expiry/global GC and no richer multi-writer coordination.
8. **Domain depth** — repository-level root-cause/security semantics and richer hackathon judging semantics remain benchmark-driven extensions.
9. **Progress tuning** — no-progress thresholds have not been tuned on a representative real-task corpus.
10. **Performance evidence** — matched-control infrastructure exists, but repeated real-provider benchmarks are still required before claiming that the harness improves solve quality/cost/time.

## Promotion gate

Promotion to `main` requires the final `develop` commit to report:

```text
harness/full-regression = success
```

That status represents:

```text
editable package install
-> compile
-> CLI/TUI module + console entrypoint smoke
-> full pytest
-> core freeze audit
-> Stage03-08 regression/adversarial/cost probes
-> Stage02 isolation/binding regression probes
```

The old `main` tip is preserved as `legacy-main-pre-integration` before `main` is moved.
