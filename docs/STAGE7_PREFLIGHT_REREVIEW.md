# Stage 07 — Context Governance Preflight Re-review

Status: **ENTRY REVIEW COMPLETE**  
Base release: `v0.7.0`  
Base branch HEAD at review start: `82f6ac2a370eb033fb51623cf530c9442eb6b978`

## Objective

Review the released Stage 06 runtime before introducing any Context Governor implementation. The purpose is to identify projection/trust defects first and prevent memory, retrieval, or summarization features from being built on an undefined model-visible context boundary.

## Findings

### C7-01 — Observation history is unbounded in Actor context

Severity if left unchanged: **HIGH**.

`RuntimeExecutionMixin._context()` serializes every `state.observations` entry. Long runs therefore grow model-visible context monotonically and repeated identical observations consume the same context budget repeatedly.

Required correction: deterministic duplicate collapse + bounded recent observation selection.

### C7-02 — Preview truncation only handles long strings

Severity: **HIGH**.

`_store_tool_observation()` truncates a direct string preview at 8000 characters, but nested dict/list/object outputs are retained as full Python values and later copied into context. Large structured outputs can therefore bypass the preview bound.

Required correction: context-time canonical textual preview with per-item and aggregate character budgets regardless of original value type.

### C7-03 — Ordinary GoalContract constraints are missing

Severity: **CRITICAL for task fidelity**.

`GoalContract` distinguishes `constraints` and `pinned_constraints`, but `_context()` exposes only pinned constraints and acceptance. A valid ordinary constraint can therefore disappear from the model-visible prompt.

Required correction: all `constraints` and `pinned_constraints` are mandatory projection fields.

### C7-04 — Trust classes are flattened into one context object

Severity: **HIGH**.

Verified facts, hypotheses, refuted hypotheses, observations, failures, and control state are siblings without an explicit trust namespace. Claims contain status/authority metadata, but observations have no trust or instruction-authority label.

Required correction: explicit `trusted`, `untrusted`, `control`, and `goal_contract` namespaces.

### C7-05 — Untrusted observation text has no instruction-boundary marker

Severity: **HIGH**.

Tool/remote output may contain arbitrary text. The built-in `LLMController` JSON-serializes the context directly into the user prompt, while the system prompt has no Stage-07 rule saying observation/hypothesis text is data rather than instruction authority.

Required correction: observation/speculation labels plus built-in model-system warning.

### C7-06 — Supersession metadata is not honored by context projection

Severity: **HIGH**.

`Claim` has `superseded_by`, yet `_context()` copies every fact as current fact. A claim explicitly marked superseded can therefore still be represented as current truth to the Actor.

Required correction: exclude superseded facts from current trusted facts and expose their keys separately for audit visibility.

### C7-07 — `valid_until` cannot safely use current wall time

Severity: **HIGH if interpreted naively**.

`Claim.valid_until` exists, but the durable run has no persisted deterministic context-as-of clock. Evaluating expiry against the host's current time would make identical resumed state project differently.

Required correction: surface validity metadata but do not interpret expiration in Stage 07.

### C7-08 — Mandatory trusted/task state cannot be safely dropped by generic truncation

Severity: **CRITICAL if dropped**.

Goal, acceptance, constraints, current verified facts, terminal/recovery state, and tool execution-safety metadata are required for correct decisions. A generic total-size truncator could silently remove them.

Required correction: context budget applies only to compressible sections. Mandatory sections are never silently dropped.

### C7-09 — Recent failure window is hard-coded, not policy/provenance

Severity: **MEDIUM/HIGH**.

`recent_failures = state.failures[-5:]` embeds a context-selection semantic in runtime code. Changing it alters Actor-visible execution semantics but currently is not part of configuration provenance.

Required correction: move failure selection count into `ContextPolicy` and fingerprint it.

### C7-10 — Tool descriptions are unbounded

Severity: **MEDIUM**.

All tools must remain visible, but arbitrarily large descriptions can dominate context.

Required correction: preserve every tool name, side-effect class, and idempotence while bounding only description text.

### C7-11 — Context policy does not exist in manifest provenance

Severity: **HIGH**.

Observation count, preview limits, speculation limits, failure window, and tool-description limits all change Actor-visible behavior.

Required correction: complete `ContextPolicy.descriptor()` in `_config_descriptor()`.

### C7-12 — Duplicate observations can crowd out more useful recent evidence

Severity: **HIGH**.

Even after imposing `max_observations`, naive last-N selection allows repeated identical evidence to occupy the entire window.

Required correction: collapse observations by content-address digest before applying the recent-group limit, and retain occurrence count.

### C7-13 — Context reduction must not delete evidence

Severity: **CRITICAL if violated**.

A projection layer must not rewrite/delete artifacts or remove durable observations merely to reduce prompt size.

Required correction: projection is read-only; representative artifact refs remain visible for selected groups; omitted evidence remains durable.

### C7-14 — Projection itself must not create a new persistence/crash boundary

Severity: **HIGH**.

Writing new state/checkpoints while building context could separate controller cursor, state, and Actor-step semantics established by Stage 03/05.

Required correction: projection is pure with respect to HarnessState/checkpoint/recovery/progress.

### C7-15 — Tokenizer-specific budgeting would harm determinism/portability at this Stage

Severity: **MEDIUM design risk**.

The core runtime has no tokenizer dependency and model adapters can vary. A tokenizer-dependent context contract would bind semantics to model-specific packages/revisions.

Required correction: Stage 07 uses deterministic item/character budgets. Token optimization is deferred.

### C7-16 — Raw HarnessState remains available to in-process Controller adapters

Severity: **boundary clarification**.

`controller.decide(goal, state, context)` receives a copied full state for deterministic controller logic. The built-in `LLMController` ignores this state and serializes only `goal + context`, but a custom in-process controller could deliberately relay raw state.

Required correction: define custom Controller adapters as trusted integration code. Stage 07's untrusted-model guarantee applies to the model-visible projection and hardens the built-in LLM adapter. A later API redesign may narrow the controller protocol itself.

## Entry decision

No finding requires reopening Stage 01–06. These are defects/constraints of the new Context Governance semantic axis.

**Stage 07 may proceed only under the frozen Context Projection Contract.**
