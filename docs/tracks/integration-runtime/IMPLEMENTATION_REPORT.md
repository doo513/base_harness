# Integration Runtime — Implementation Report

Date: 2026-08-19
Branch: `develop`
Baseline: verified-state Kernel / Stage 00-08 freeze line (`0.9.1`)

## Purpose

This work turns the frozen verified-state Kernel into a usable development/hackathon runtime without weakening the original authority boundaries. The integration work follows this rule:

```text
Model / Agent / Memory / MCP / Plugin / Domain guidance
                    ↓
             may propose / act
                    ↓
              Kernel boundary
                    ↓
Capability / Tool Runtime / Verification / Progress / Recovery / Oracle
                    ↓
          trusted state / completion
```

New integration code must not directly grant trusted truth, verified progress, or accepted completion.

## Phase status

| Phase | Main implementation | Structural result | Validation status |
|---|---|---|---|
| 00 Baseline | develop CI triggers/docs/version consistency | Core freeze preserved | CI configured; successful push-run not observable from current connector |
| 01 Workspace | explicit workspace root, managed paths, tool-workspace validation | no sandbox authority replacement | targeted tests added |
| 02 Config/Secrets | typed TOML config, env secret references | secrets remain references; config is declarative | targeted tests added |
| 03 Model Gateway | provider registry, command/OpenAI-compatible adapters, retry/fallback/telemetry | model output remains Controller proposal only | targeted tests added |
| 04 Agent Control | durable plan/tasks/dependencies/active task | workflow has no truth/progress/completion authority | targeted tests added |
| 05 Tool Contracts | input/output schemas, bounded workspace READ tools | capability/isolation path preserved | targeted tests added |
| 06 MCP/Plugin | stdio MCP + explicit installed plugins + tool normalization | external tools still pass ActionRuntime; strict isolation fails closed | targeted tests added |
| 07 Context Relevance | deterministic active-task lexical relevance view | relevance changes visibility only, never trust | targeted tests added |
| 08 Project Memory | post-run cross-run project/episodic memory + frozen retrieval snapshot | memory remains untrusted retrieval | targeted tests added |
| 09 Domain Execution | Software/Hackathon workflow, verifier-backed milestones, advisory evaluation | hard truth and soft quality remain separated | targeted tests added |
| 10 Progress Alignment | domain milestones feed existing Stage-06 task progress | raw activity is still not progress | targeted tests added |
| 11 E2E | real subprocess Model Gateway → Agent → Tool → Oracle local path | no benchmark-only execution shortcut | automated local E2E test added; live provider evidence pending |
| 12 Benchmark/Ablation | matched-control records + aggregation | mismatched controls fail closed | targeted tests added; no performance claim |
| 13 TUI | thin launcher/monitor over existing CLI | no second runtime authority | targeted tests added; interactive approvals pending |

## Major implementation map

### Workspace / runtime composition

- `harness.core.workspace.WorkspaceContract`
- designated directory becomes actor workspace root;
- temp/build/cache paths must remain under the root;
- tools declaring execution workspaces are rejected if they escape the selected root;
- OS sandboxing remains the responsibility of existing execution backends / Stage 02 security.

### Configuration / secrets

- `harness.config.HarnessConfig`
- config domains: workspace, model, MCP, plugin, memory, security;
- secret syntax currently `env:NAME` only;
- descriptors never contain resolved secret values;
- malformed/unknown extension configuration fails closed.

### Model Gateway

- `harness.model_gateway.ModelGateway`
- provider registry;
- argv-based Command provider (`shell=False`);
- OpenAI-compatible HTTP adapter;
- explicit retries/fallback aliases;
- request/token/latency telemetry;
- deterministic model-gateway revision for resume provenance;
- legacy `CommandModelAdapter` now delegates to the Gateway.

The Gateway deliberately keeps the existing `LLMController.complete(system,user)` boundary so the Kernel does not depend on provider-specific APIs.

### Agent Control

- `AgentControlState`
- objective;
- bounded task list;
- dependency DAG;
- active/pending/done/blocked state;
- persisted through `HarnessState` snapshots;
- model decisions `plan` and `task` manage workflow only.

A task marked `done` does not create a verified fact, task-progress milestone, or accepted completion.

### Tool Runtime usability

- optional tool input/output schemas;
- pre-execution argument validation;
- post-execution result validation;
- model-visible schema enrichment;
- bounded `file.read`, `directory.list`, `file.search` tools;
- `shell`/`argv` remain sandbox-owned WRITE mechanisms instead of adding unsafe in-process WRITE helpers.

### MCP / plugins

- `MCPStdioClient` / `MCPGateway`;
- modern MCP discovery with bounded legacy fallback;
- `tools/list` / `tools/call` only in v1;
- server annotations do not grant security policy;
- default MCP tool policy is conservative: `EXTERNAL + confirm + non-idempotent`;
- provider JSON Schemas are preserved for model calls without falsely claiming the local schema subset fully validates them;
- Python plugins are explicit already-installed trusted host extensions only;
- no auto-install / auto-discovery;
- strict tool isolation rejects MCP/plugin v1 because host-process isolation is not implemented.

### Context

Original Stage-07 context stays intact. `active_context` adds a deterministic relevance view derived from:

- goal / acceptance / constraints;
- Agent Control objective;
- active task title/note.

Trust and relevance remain separate:

```text
trust      → authority
relevance  → visibility priority
```

### Cross-run memory

- project/episodic memory is explicit opt-in;
- actor stages `memory_candidate.*` as an untrusted proposal;
- candidate requires registered evidence references;
- publication happens after `runtime.run()` returns;
- a run reads a frozen memory snapshot created before execution;
- later recall enters only through the existing Stage-08 retrieval path;
- memory store must not overlap actor workspace;
- records have bounded integrity envelopes.

### Software domain

Workflow:

```text
inspect
→ reproduce
→ plan
→ implement
→ targeted verification
→ regression
→ acceptance
```

Verifier-backed progress vocabulary currently includes build/test/behavior/artifact facts. Advisory quality criteria (scope, maintainability, regression risk) have no completion authority.

### Hackathon domain

Workflow:

```text
scope
→ prototype
→ build check
→ demo check
→ polish
→ rehearsal
→ acceptance
```

Hard execution classes:

- `hackathon.build_check.*`
- `hackathon.demo_check.*`
- `hackathon.rehearsal_check.*`

Soft judging criteria remain advisory and cannot pass hard checks or the final completion oracle.

### Progress / recovery

The original Stage-06 rule was intentionally not weakened. The integration bridge is:

```text
activity
→ evidence
→ domain verifier
→ verified fact
→ domain milestone
→ Stage-06 task progress
```

Planning, task checkboxes, successful tool calls, retrieval, memory, and soft evaluation cannot manufacture progress-reset credit.

### E2E / evaluation

Automated local E2E exercises:

```text
Command Model subprocess
→ Model Gateway
→ LLMController
→ plan/task
→ shell workspace mutation
→ durable observation artifact
→ completion request
→ independent fixed acceptance command
→ accepted completion
```

Evaluation infrastructure binds matched controls for task/model/profile/tools/budget/oracle/environment and rejects comparisons when those differ.

### TUI

`python -m harness.tui` provides:

- new run launcher;
- resume launcher;
- persisted-run inspection;
- live stdout/stderr + metrics/events/tool-call monitoring.

The TUI calls the existing CLI as argv and is read-only with respect to runtime state. It does not reimplement Kernel policy.

## Review findings fixed during implementation

The phase-by-phase structural re-review found and corrected several integration defects before advancing:

1. runtime workspace and profile tool workspace could diverge → explicit workspace contract + fail-closed tool workspace validation;
2. legacy command-model path used `shell=True` → replaced by argv-based provider execution;
3. model/tool interface lacked machine-readable arguments → schema-aware tool contracts;
4. external tool schemas were not represented in resume provenance → schema hashes stamped into tool provenance;
5. MCP server annotations could otherwise be mistaken for authorization → operator-owned policy only, conservative default;
6. replacing profiles during tool composition would obscure domain-profile provenance → augment original profile identity instead;
7. cross-run memory could destabilize a currently resumable run → frozen run-start snapshot + post-run publication;
8. Hackathon hard checks initially lacked explicit direct verifier identity/coverage → verifier result binding corrected;
9. progress integration test used an outdated result key → corrected to the actual `progress_reasons` contract.

## Current validation statement

### What has been validated in code/design

- each integration phase has focused regression tests in `tests/test_integration_*.py` or the E2E suite;
- new execution paths preserve the Kernel-owned verification/completion boundary by construction;
- configuration, schemas, extension identity, memory records, and matched-control evaluation have fail-closed validation paths;
- phase-specific MD files record the evidence, design decision, structural review, validation focus, and limitations.

### What is **not yet proven**

A successful full `pytest` / GitHub Actions run for the latest integrated `develop` HEAD has not been observable through the current connector/environment. Therefore this report does **not** label the integrated branch release-ready or recommend promotion to `main` yet.

Before promotion, require:

```text
full pytest                                      PASS
Stage 02-08 existing probes                     PASS
new integration tests                           PASS
local E2E Software/Hackathon                    PASS
no unresolved Critical/High structural defect  PASS
```

For real capability/performance claims additionally require:

```text
live provider case(s)                           evidence recorded
real development/hackathon task corpus          repeated runs
matched baseline/harness controls               PASS
ablation report                                 generated
false completion / solve / token / time metrics reviewed
```

## Known remaining limitations

These are follow-up limitations, not hidden completion claims:

1. **TUI approval workflow** — MCP default `confirm` cannot yet be interactively approved through a persisted Kernel approval contract.
2. **Provider coverage** — native Anthropic/Gemini adapters and harness-level streaming are not implemented.
3. **MCP coverage** — HTTP transport and server-initiated sampling/elicitation/resources/prompts/tasks are outside MCP gateway v1.
4. **Plugin isolation** — Python plugins execute as explicitly trusted host extensions; strict-isolation mode rejects them.
5. **Context relevance** — deterministic lexical relevance is intentionally simpler than semantic/embedding ranking.
6. **Memory lifecycle** — no decay/expiry/global GC or multi-writer coordination beyond atomic record writes.
7. **Domain semantics** — Software repository understanding/root-cause/security properties and richer Hackathon criteria remain benchmark-driven expansions.
8. **Progress thresholds** — no-progress thresholds have not been tuned against a representative real-task corpus.
9. **Performance evidence** — infrastructure exists, but no harness-superiority claim is made without real matched repeated evaluation.

## Promotion rule

Keep development on `develop`. Do not modify the frozen `preprocessing` snapshot. Promote to `main` only after the latest integrated HEAD has observable full regression/E2E evidence and the remaining blocking findings are zero.
