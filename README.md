# Verified-State Harness

`base_harness` is a model-driven task harness that allows an LLM Actor to plan and request actions while the **Harness retains authority over execution, evidence, verification, recovery, memory admission, and accepted completion**.

```text
User
 └─ goal / workspace / profile / model / permission
        ↓
TUI / CLI
        ↓
LLM Actor
 └─ plan / tool / retrieve / propose / complete request
        ↓
Verified-State Harness
 ├─ Workspace boundary
 ├─ Tool & capability policy
 ├─ Evidence store
 ├─ Verification contracts
 ├─ Progress control
 ├─ Recovery / resume
 ├─ Retrieval / Project Memory
 └─ Completion Oracle
        ↓
Verified result + persisted evidence
```

> **The Actor may propose and act; only Harness-side verification/oracles may promote trusted truth or accepted completion.**

Current package version: **0.10.0**.

Development artifact / evidence-oriented implementation summary:

- [`BASE_HARNESS_DEVELOPMENT_ARTIFACT_2026-08-24.md`](docs/tracks/integration-runtime/BASE_HARNESS_DEVELOPMENT_ARTIFACT_2026-08-24.md)
- [`RECENT_EVOLUTION_EVIDENCE_REPORT_2026-08-20.md`](docs/tracks/integration-runtime/RECENT_EVOLUTION_EVIDENCE_REPORT_2026-08-20.md)
- [`CI_STATUS.md`](docs/tracks/integration-runtime/CI_STATUS.md)

---

## 1. Who controls what?

| Subject | Responsibility |
| --- | --- |
| **User** | Chooses the goal, workspace, profile/domain, model/provider and allowed execution settings. |
| **LLM Actor** | Proposes plans, tool calls, retrieval, hypotheses and completion requests. |
| **Harness** | Decides what is permitted, executes tools, stores evidence, verifies claims, controls memory admission/retrieval, recovery and final completion. |

In short:

```text
User defines intent and boundaries
        ↓
LLM proposes how to work
        ↓
Harness executes and verifies
```

---

## 2. Installation

Python **3.11+** is required.

### Linux / WSL / macOS

```bash
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

### Windows PowerShell

```powershell
git clone https://github.com/doo513/base_harness.git
cd base_harness
git checkout main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Check the entry points:

```bash
verified-harness --help
verified-harness-tui --help
```

---

## 3. Recommended usage: TUI

```bash
cd /path/to/project
verified-harness-tui
```

Or specify the workspace explicitly:

```bash
verified-harness-tui --workspace /path/to/project
```

The normal interface is a natural-language task:

```text
❯ 로그인 API에 rate limit을 추가하고 회귀 테스트까지 해줘
❯ 프로젝트 구조를 분석해서 architecture_review.md를 작성해줘
❯ 이 오류의 원인을 찾아 수정하고 검증해줘
```

Operational events are condensed to signals such as:

```text
◇ Plan     Actor plan/checklist
● Tool     tool execution
✓ Verify   Harness verification
↻ Retry    recovery/strategy change
✕ Issue    meaningful failure
✓ Final    completion-oracle result
```

Esc interrupts a running task; Ctrl+C is retained as a fallback. Persisted state can later be inspected or resumed.

---

## 4. CLI

Use the CLI for CI, scripts and reproducible experiments.

```bash
verified-harness \
  --config harness.toml \
  --profile software \
  --workspace /path/to/project \
  --run-dir ./runs/task-01 \
  --goal "Implement the requested change and verify it." \
  --accept-command "python -m pytest -q" \
  --max-steps 30
```

Profiles currently include:

```text
demo
software
hackathon
ctf
```

Domain-specific acceptance semantics belong in profiles; the common kernel keeps generic evidence and authority rules.

---

## 5. Model providers

`ModelGateway` separates provider transport/protocol behavior from the verified-state kernel.

### Generic OpenAI-compatible provider

```toml
[models.primary]
provider = "openai-compatible"
model = "example-model"
endpoint = "https://provider.example.com/v1"
api_key = "env:MODEL_API_KEY"
timeout_seconds = 120
```

### Ollama

Ollama has an explicit local-provider route rather than relying only on generic OpenAI compatibility.

```toml
default_model = "ollama"

[models.ollama]
provider = "ollama"
model = "your-local-model"
endpoint = "http://127.0.0.1:11434"
timeout_seconds = 120

[models.ollama.options]
temperature = 0
max_tokens = 1024
think = false
```

The provider uses the native Ollama chat route and structured JSON Schema output.

### LM Studio

```toml
default_model = "lmstudio"

[models.lmstudio]
provider = "lm-studio"
model = "your-loaded-model"
endpoint = "http://127.0.0.1:1234/v1"
timeout_seconds = 120

[models.lmstudio.options]
temperature = 0
max_tokens = 1024
```

LM Studio uses its OpenAI-compatible chat endpoint with JSON Schema structured output.

### Local protocol repair

Small/local models may produce truncated JSON, Markdown-fenced JSON, or schema-invalid decisions. These are treated as **provider protocol failures**, not immediately as task failures.

```text
model output
   ↓
Gateway structured-output validation
   ├─ valid → Controller
   └─ invalid/truncated/schema error
          ↓
       one bounded repair attempt
          ↓
       valid → Controller
       fail  → classified ProviderError
```

Representative error classes include:

```text
protocol_truncated
protocol_invalid_json
protocol_schema
empty_response
rate_limit
network_error
timeout
```

This prevents a malformed local-model response from automatically expanding into repeated Harness `repair → replan → strategy switch` loops.

---

## 6. Verified State and Evidence

Actor text is not trusted state.

```text
Actor proposal
   ↓
Hypothesis
   ↓
Evidence artifact
   ↓
Verifier chain
   ↓
Verification contract
   ↓
VERIFIED fact
```

Verification levels include:

```text
SCHEMA
STRUCTURAL
LOGICAL
TRANSITION
EXECUTION
EXTERNAL_ORACLE
```

Content-addressed artifacts are verified before being used as trusted evidence. A model cannot place a claim directly into `facts`.

---

## 7. Completion

A model decision such as:

```json
{"kind":"complete","payload":{"reason":"done"}}
```

is only a **completion request**.

The Harness-side completion oracle evaluates the acceptance contract and decides whether the run is actually complete.

For software/hackathon tasks this may include fixed acceptance commands. Command oracles receive an explicit execution backend instead of silently creating a separate host-local execution boundary.

---

## 8. Progress control and recovery

Activity is not automatically progress.

```text
new tool activity           → no trusted progress credit by itself
verified fact advancement   → epistemic progress
profile milestone advance   → task progress
```

The kernel tracks repeated decision families, no-progress streaks and strategy generations. Repeated planning or repeated reads can therefore trigger replan/switch-strategy rather than run indefinitely.

Run state is persisted through manifests, checkpoints, event logs and tool receipts. Non-idempotent actions are guarded so resume does not blindly repeat an uncertain side effect.

---

## 9. Retrieval and Context Governance

The Actor may request retrieval, but the Kernel owns retrieval policy fields such as scope, top-k, ranking and admission.

```text
Actor query
    ↓
Kernel retrieval policy
    ↓
retrieval result
    ↓
untrusted context
```

Retrieved text:

- has no instruction authority;
- cannot override system/kernel policy;
- does not become a verified fact automatically;
- does not count as progress merely because it was retrieved;
- is bounded by deterministic content/context limits.

---

## 10. Project Memory

### Current stable implementation

The currently active common memory implementation is **Project Memory v1**.

```text
run evidence
    ↓
memory_candidate.*
    ↓
post-run admission
    ↓
ProjectMemoryStore
    ↓
next run: frozen memory snapshot
    ↓
untrusted lexical retrieval
```

Current properties:

- `project` and `episodic` memory kinds;
- explicit opt-in;
- evidence reference required;
- post-run publication;
- memory root separated from Actor workspace;
- integrity-checked, bounded records;
- frozen snapshot for each run;
- every remembered item remains `untrusted_project_memory`.

Important:

```text
remembered ≠ verified
retrieved  ≠ instruction
memory     ≠ completion authority
```

### P2 memory direction

P2-A~D has been researched and designed around:

```text
A. versioned lifecycle / supersession / current-state resolver
B. semantic evidence binding / verification history
C. typed memory + BM25 + bounded query-time assembly
D. memory→decision→artifact lineage and impact analysis
```

The previous compressed staging attempt for this P2 implementation failed integrity validation. Therefore **P2-A~D is documented design work, not an active stable runtime feature yet**. The failed one-shot workflow/payload was removed rather than being treated as completed implementation.

---

## 11. Workspace and security boundary

The workspace is an explicit Actor filesystem boundary.

```text
WorkspaceContract.root
      ↓
workspace tools
      ↓
relative paths inside root
```

Execution currently supports the established local/Linux namespace backend paths. Linux namespace isolation has separate probes and binding checks; local execution must not be described as a strong sandbox.

MCP, Skills and plugins do not gain authority simply by being discovered or installed.

```text
Skill guidance / MCP tool
        ↓
Tool + security policy
        ↓
Evidence
        ↓
Verification
```

---

## 12. MCP and Skills

Useful TUI controls include:

```text
/mcp list
/mcp search <query>
/skills [query]
/model [alias]
/workspace [path]
/permissions
/resume <run-dir>
/inspect <run-dir>
```

Workspace-local Skills can live under:

```text
<workspace>/.harness/skills/<skill-name>/SKILL.md
```

Skill metadata is guidance/capability composition; it does not bypass runtime permission checks.

---

## 13. Run files

A run typically persists:

```text
run_manifest.json
checkpoint.json
events.jsonl
tool_calls.jsonl
metrics.json
artifacts/
receipts/
final_result.json
```

Use:

```text
/inspect <run-dir>
/resume <run-dir>
```

to review or continue persisted work.

---

## 14. Validation

The main regression workflow checks more than unit tests:

```text
compileall
CLI/TUI entrypoints
full pytest
core-freeze audit
resume
semantic verification
recovery/adversarial/crash-window
progress control
context governance
retrieval/integrity
namespace/tool-binding probes
```

After removing obsolete one-shot staging placeholders and failed payloads, the latest validated development baseline at the time of this README update was:

```text
compile                         PASS
full pytest                     323 passed, 7 skipped
all listed Stage 02~08 gates    PASS
```

See [`CI_STATUS.md`](docs/tracks/integration-runtime/CI_STATUS.md) for the latest generated result.

---

## 15. Development status

### Stable/common runtime surface

- Verified-State Kernel
- Workspace boundary
- Evidence/artifact integrity
- Verification contracts
- Completion Oracle
- Progress control
- Recovery + durable resume
- Context governance
- Retrieval
- Project Memory v1
- TUI / CLI
- MCP / Skills integration boundary
- Generic OpenAI-compatible model provider
- Ollama structured provider
- LM Studio structured provider
- Gateway-level local protocol validation/repair

### Next work

1. Re-implement P2 Memory lifecycle/evidence-binding as normal reviewed source code, not compressed staging payloads.
2. Add typed memory retrieval/query-time assembly after lifecycle correctness is established.
3. Add memory lineage impact analysis before attempting automatic selective rollback.
4. Benchmark Ollama/LM Studio models end-to-end, including structured-output failure rate and step efficiency.
5. Complete a common Environment Provider layer for Docker/VM/Remote targets after isolated validation.

---

## 16. Development evidence

For the causal development history, failure analysis and remaining limitations, read:

- [`BASE_HARNESS_DEVELOPMENT_ARTIFACT_2026-08-24.md`](docs/tracks/integration-runtime/BASE_HARNESS_DEVELOPMENT_ARTIFACT_2026-08-24.md)
- [`HARNESS_EVIDENCE_BASED_ARCHITECTURE_REVIEW_2026-08-21.md`](docs/tracks/integration-runtime/HARNESS_EVIDENCE_BASED_ARCHITECTURE_REVIEW_2026-08-21.md)
- [`POST_IMPLEMENTATION_AUDIT.md`](docs/tracks/integration-runtime/POST_IMPLEMENTATION_AUDIT.md)
- [`CI_STATUS.md`](docs/tracks/integration-runtime/CI_STATUS.md)
