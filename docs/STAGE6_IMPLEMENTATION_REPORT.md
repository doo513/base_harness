# Stage 06 — Loop / Progress Control Implementation Report

Status: **PASS candidate for v0.7.0**  
Branch: `research/verified-state-stage03`  
Final candidate: `3188ea75f7ca3d503cd8557cd7dd8bd562eaa2d4` (`v0.7.0-rc3`)

## 1. Objective

Stage 06 adds deterministic, kernel-owned progress accounting on top of the Stage 05 recovery state machine. The purpose is not to decide whether an Actor is “reasoning well,” but to bound inspectable repeated/no-progress execution without trusting Actor narrative.

The resulting control flow is:

```text
Actor Decision
  -> capture trusted progress baseline
  -> dispatch through existing Stage 01-05 gates
  -> if a specific failure already exists: preserve it
  -> otherwise compare deterministic progress signals
       verified fact semantic content changed?
       novel successful observation content appeared?
  -> progress: reset local no-progress windows
  -> no progress: advance family/global windows
  -> threshold: schedule typed NO_PROGRESS via Stage 05
  -> repeated NO_PROGRESS: Stage 05 SWITCH_STRATEGY
  -> too many generations without progress: STRATEGY_EXHAUSTED
  -> Stage 05 ESCALATE terminal
```

Progress is a **control signal only**. It never grants truth authority, never commits a fact by itself, never accepts completion, and never executes a tool or recovery transition directly.

## 2. Entry re-review

Before implementation, the Stage 05 release was re-read from a progress-control perspective. Twelve design blockers were identified and documented in `STAGE6_PREFLIGHT_REREVIEW.md`.

The highest-risk findings were:

1. artifact-reference count is not evidence novelty because the same bytes receive step-specific ref names;
2. hypotheses/refutations are Actor-controlled and cannot be authoritative progress;
3. exact payload identity alone is vulnerable to whitespace/narrative churn;
4. family identity alone can incorrectly block legitimate successful exploration;
5. generic NO_PROGRESS must never supersede a specific Stage 05 security/persistence/tool/verification failure;
6. recovery transitions consume harness steps but are not Actor progress samples;
7. progress counters must survive checkpoint/resume;
8. progress policy thresholds are execution semantics and belong in manifest provenance;
9. an extra progress checkpoint could split controller cursor from normal Actor-step persistence;
10. failed output must not manufacture progress;
11. strategy switch is control, not progress;
12. evidence must pass content-address integrity verification before it can be recognized as progress.

No existing Stage 01-05 guarantee had to be weakened.

## 3. Implementation

### 3.1 `ProgressPolicy`

A deterministic policy object defines:

- `family_repeat_limit`;
- `no_progress_streak_limit`;
- `max_strategy_generations_without_progress`.

The full descriptor is included in the run configuration fingerprint. Resume under different progress semantics therefore fails closed through the existing reproducibility gate.

### 3.2 `ProgressState`

Durable progress state is part of `HarnessState.snapshot()`:

- current progress strategy generation;
- consecutive no-progress count;
- last decision family;
- same-family repeat count;
- evaluation count;
- recognized progress count;
- last progress step/generation/reasons;
- threshold-trigger count.

This makes interruption unable to reset the loop window silently.

### 3.3 Decision identity

Two signatures are computed for Actor decisions.

**Family identity** is intentionally coarse:

```text
propose:key
verify_claim:key
refute:key
tool:tool-name
complete
```

**Exact identity** canonicalizes Actor payload mapping order and cosmetic string whitespace while preserving numbers/list order. Actor-controlled `complete.reason` and `refute.reason` are excluded from repetition identity.

Exact-signature novelty is never treated as progress by itself.

### 3.4 Progress authority

Recognized progress has two deterministic sources.

#### Verified fact semantic content

The fingerprint contains verified fact:

```text
key + value + status + authority
```

Evidence-reference metadata is excluded. Reattaching another evidence ref to the same fact cannot manufacture progress.

Fact values themselves are preserved exactly because whitespace and formatting can be semantically meaningful.

#### Successful observation content

A successful observation can be progress only if:

1. its `artifact://` reference encodes a valid SHA-256;
2. current raw artifact bytes still hash to that digest;
3. JSON decodes to an object whose `ok` field is exactly `true`;
4. its canonical JSON content fingerprint has not appeared in prior successful observations.

JSON mapping-key insertion order is cosmetic. String values are preserved exactly.

### 3.5 Historical evidence integrity

Every Actor boundary re-verifies all historical successful-observation artifacts used by progress accounting. If a prior artifact has disappeared or changed, the Actor is not called. The Kernel schedules typed `PERSISTENCE_ERROR`, which Stage 05 routes to durable terminal `CHECKPOINT_STOP`.

This is deliberately conservative and creates a performance tradeoff documented later.

### 3.6 Specific failure precedence

Stage 06 evaluates the Actor sample but cannot schedule generic `NO_PROGRESS` if dispatch already created a pending Stage 05 recovery.

Examples:

```text
TOOL_ERROR          stays TOOL_ERROR
SECURITY_VIOLATION  stays terminal security failure
PERSISTENCE_ERROR   stays terminal persistence failure
VERIFICATION_FAILED stays verification failure
```

Stage 06 cannot downgrade these into a generic loop-recovery path.

### 3.7 Threshold behavior

Two local deterministic windows exist:

- same-family no-progress window;
- global consecutive no-progress window across changing families.

One threshold crossing schedules one typed failure and resets the local window. The global failure uses a stable action/signature independent of the latest family so alternating behavior still participates in Stage 05 repeat escalation.

### 3.8 Strategy generation

A Stage 05 `SWITCH_STRATEGY` resets local Stage 06 repeat windows, but the switch itself is not progress.

Historical evidence remains globally known across strategy generations. Rediscovering identical successful content after a switch is not novel.

The generation of the last actual progress event remains durable. If the configured number of strategy generations passes without another recognized progress event, Stage 06 schedules `STRATEGY_EXHAUSTED`; Stage 05 terminally applies `ESCALATE`.

### 3.9 Recovery is not an Actor sample

`RuntimeProgressMixin` runs only around an Actor Decision. A Stage 05 recovery transition leaves `progress.evaluations` unchanged, preventing recovery itself from accelerating loop escalation.

## 4. Candidate history and errors found

| Candidate | Automated result | Re-review finding |
|---|---|---|
| rc1 | 105 passed / 5 skipped; all Stage 03-06 probes green | Historical artifact tamper was not fully rechecked; baseline integrity exceptions could escape typed failure handling; global NO_PROGRESS action destabilized repeat identity; verified fact evidence-ref churn could look like progress. |
| rc2 | 109 passed / 5 skipped; boundary probe green | Reusing Actor whitespace normalization for verified facts/evidence could collapse semantically different source/config content. |
| rc3 | 112 passed / 5 skipped; all direct probes green | Content and decision normalization separated; no unresolved Critical/High Stage 06 defect found in final review. |

The important methodological point is that rc1 and rc2 were **not promoted simply because CI was green**. The implementation was re-read after each passing candidate and each newly discovered defect became an explicit regression/probe.

## 5. Validation methodology

```text
preflight architecture review
-> freeze deterministic Progress Contract
-> implement durable state/policy
-> add unit/integration tests
-> direct base progress probe
-> adversarial identity/tamper/failure-precedence probe
-> resume continuation/policy-drift probe
-> historical-integrity/content-boundary probe
-> strategy/exhaustion/recovery-boundary probe
-> full Stage 03-05 regression
-> final logic/implementation/structure re-review
```

No earlier security, persistence, verification, recovery, or completion gate was weakened to make a Stage 06 test pass.

## 6. Final candidate evidence

GitHub Actions run `31937830666`:

```text
compileall                              PASS
pytest                                  112 passed / 5 skipped
Stage 03 resume                         4 / 4 PASS
duplicate external actions             0
Stage 04 semantic matrix                8 / 8 PASS
Stage 04 FP / FN                        0 / 0
Stage 05 base/adversarial/terminal      PASS
Stage 05 crash-window/strategy          PASS
Stage 06 base progress                  3 / 3 PASS
Stage 06 adversarial                    3 / 3 PASS
Stage 06 resume                         3 / 3 PASS
Stage 06 boundary                       4 / 4 PASS
Stage 06 strategy                       6 / 6 PASS
Actor self-progress acceptances         0
cosmetic decision evasions              0
specific failure supersessions          0
artifact-tamper progress acceptances    0
historical-tamper Actor continuations   0
resume progress divergence              0
progress-policy drift acceptances       0
global repeat identity divergence       0
fact-metadata false progress            0
whitespace false no-progress            0
recovery Actor samples                  0
failed-output progress acceptances      0
strategy exhaustion nonterminal cases   0
```

The five skipped tests remain hosted-environment live Linux namespace tests. They are not Stage 02 production-isolation proof and do not replace the previously recorded direct Stage 02 attack evidence.

## 7. Final guarantee boundary

Stage 06 proves **deterministic syntactic progress control**, not semantic usefulness.

It does not claim:

- that novel evidence is relevant to the goal;
- that adding a new verified but irrelevant fact is useful progress;
- that a changing timestamp/nonce/random sample should be treated as no progress;
- semantic equivalence across differently encoded evidence;
- embedding/LLM-based loop understanding;
- planner quality or model reasoning quality.

A tool that legitimately emits different canonical content on every call can continue to produce syntactic novelty until the hard budget ends the run.

## 8. Performance boundary

Historical successful artifacts are re-hashed at each Actor boundary. With an ever-growing observation history, cumulative verification work can grow approximately quadratically in the number of successful observations.

This is a **Medium performance limitation, not a correctness bypass**. The current choice prefers tamper detection before Actor continuation over optimization. A future implementation may replace repeated full scans with an immutable/sealed artifact store or another integrity-preserving incremental structure, but Stage 06 does not weaken integrity to optimize it.
