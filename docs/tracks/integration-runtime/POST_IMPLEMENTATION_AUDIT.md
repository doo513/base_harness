# Post-Integration Functional Audit

Date: 2026-08-19
Scope: integrated runtime on `develop`, immediately before promotion to `main`.

This document supersedes the pre-validation wording in the earlier integration implementation report where the latest full CI result was not yet observable.

## Audit rule

A feature is counted as implemented only when its executable source exists and the public entrypoint can be exercised by CI. Documentation or tests alone are not implementation evidence.

## Findings discovered in this audit

| Finding | Severity | Status | Action |
|---|---:|---|---|
| `PHASE13_TUI.md` and TUI tests existed while `src/harness/tui.py` was absent | High | FIXED | implemented `harness.tui` |
| no installed TUI console entrypoint | Medium | FIXED | added `verified-harness-tui` |
| CI did not explicitly smoke CLI/TUI entrypoints | High process defect | FIXED | added module + console-script smoke gate |
| regression CI only targeted `develop` | Medium | FIXED | CI now targets `develop` and `main` |
| CI result was not observable through the current connector | High process defect | FIXED | publish commit status and persistent `CI_STATUS.md` ledger |
| README did not provide end-user setup / model API / TUI / CLI instructions | Medium | FIXED | README operational guide added |
| integration enrichment made Stage-07 standalone context fixtures require `profile` / `retrieval_gateway` | High compatibility regression | FIXED | restored optional post-Stage08 enrichment without weakening Stage-07 contract |
| new context-relevance tests constructed invalid `GoalContract` objects without mandatory acceptance criteria | Medium test defect | FIXED | corrected test inputs; mandatory GoalContract validation remains unchanged |

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
CTF profile                 present
Progress control            present
Recovery                    present
Verification/oracles        present
Resume/persistence          present
Evaluation/ablation         present
CLI                         present
TUI                         present
```

## Final validation evidence

Validated source commit:

```text
e098ae610cf5297a6b9883bf57f63dff12f97593
```

Observable commit status:

```text
harness/full-regression = success
```

Persisted CI evidence was committed immediately after the validated source commit and records:

```text
editable install + pip check                       PASS
compile                                            PASS
CLI module entrypoint                              PASS
TUI module entrypoint                              PASS
CLI installed console entrypoint                   PASS
TUI installed console entrypoint                   PASS
full pytest                                        PASS
core freeze audit                                  PASS
Stage 03-08 regression/adversarial/cost probes    PASS
Stage 02 isolation/binding regression probes      PASS
```

Full pytest result:

```text
268 passed, 7 skipped in 27.71s
```

The skips are environment-dependent isolation cases and are not treated as proof of unavailable production isolation. The existing Stage-02 guarantee boundary remains unchanged.

## Remaining functional limitations

These do not block basic Software/Hackathon/CTF runs through the implemented runtime surface, but they are real capability gaps and must not be described as implemented.

1. **Interactive MCP approval** — MCP tools default to confirmation, but no persisted Kernel-owned approval request/response UI exists yet. TUI cannot interactively approve those calls.
2. **Strong Windows execution isolation** — the strong namespace backend is Linux-specific. `local` execution is usable for local development but is not a strong sandbox boundary.
3. **Provider breadth / streaming** — native Anthropic/Gemini adapters and harness-level streaming are absent. Gemini can be connected through an OpenAI-compatible endpoint.
4. **MCP breadth** — v1 supports stdio tool discovery/calls, not HTTP transport, resources, prompts, sampling, elicitation, or tasks.
5. **Plugin isolation** — installed Python plugins are trusted host extensions; strict isolation rejects this path.
6. **Context ranking** — active-context relevance is deterministic lexical ranking, not semantic/embedding ranking.
7. **Memory lifecycle** — no decay/expiry/global GC and no richer multi-writer coordination.
8. **Domain depth** — repository-level root-cause/security semantics and richer hackathon judging semantics remain benchmark-driven extensions.
9. **Progress tuning** — no-progress thresholds have not been tuned on a representative real-task corpus.
10. **Performance evidence** — matched-control infrastructure exists, but repeated real-provider benchmarks are still required before claiming that the harness improves solve quality, cost, or elapsed time.

## Promotion decision

The integration release gate is satisfied for the implemented runtime surface:

```text
actual TUI source / entrypoint                   PASS
full pytest                                      PASS
Stage 02-08 regression probes                    PASS
integration tests                                PASS
core freeze audit                                PASS
Critical/High defects found by this audit        FIXED
```

The former `main` tip was preserved before promotion as:

```text
legacy-main-pre-integration
```

`preprocessing` remains frozen. After this final documentation change itself passes the same CI gate, the integrated `develop` line may be promoted to `main`.
