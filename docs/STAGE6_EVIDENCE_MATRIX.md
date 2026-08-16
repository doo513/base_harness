# Stage 06 — Evidence Matrix

Status: **PASS candidate**  
Candidate: `v0.7.0-rc3` / `3188ea75f7ca3d503cd8557cd7dd8bd562eaa2d4`  
Candidate CI: GitHub Actions `31937830666`

## Automated regression

| Evidence | Result | Purpose |
|---|---:|---|
| `python -m compileall -q src tests scripts` | PASS | Syntax/import compilation gate |
| `pytest -q` | 112 passed / 5 skipped | Full unit/integration regression |
| Stage 03 resume probe | 4/4 PASS | Existing persistence/resume guarantee |
| Stage 04 semantic probe | 8/8 PASS, FP=0, FN=0 | Existing semantic verification guarantee |
| Stage 05 recovery probe | PASS | Kernel-owned recovery guarantee |
| Stage 05 adversarial probe | PASS | Failure identity / budget / audit linkage |
| Stage 05 terminal probe | PASS | Persistence ambiguity / budget terminal semantics |
| Stage 05 crash-window probe | PASS | Durable recovery scheduling |
| Stage 05 strategy-generation probe | PASS | Repeat scope after strategy switch |

Five skipped tests are hosted-runner live Linux namespace tests and are not used as Stage 02 production evidence.

## Stage 06 direct evidence

### Base progress probe — `stage6_progress_probe.py`

| Scenario | Result | Important observation |
|---|---:|---|
| Duplicate successful content | PASS | 3 observations, one content digest, only first recognized as progress; one NO_PROGRESS failure |
| Actor speculative churn | PASS | 0 progress events; speculative proposals cannot self-promote progress |
| Distinct successful content | PASS | 3 distinct successful observations recognized as 3 progress events |

### Adversarial probe — `stage6_progress_adversarial_probe.py`

| Scenario | Result | Important observation |
|---|---:|---|
| Cosmetic decision identity evasion | PASS | JSON key order/whitespace and completion-reason churn do not manufacture new control identity |
| Specific failure precedence | PASS | TOOL_ERROR preserved; generic NO_PROGRESS does not supersede it |
| New artifact tamper | PASS | Integrity error occurs before tampered artifact can become progress |

### Resume probe — `stage6_progress_resume_probe.py`

| Scenario | Result | Important observation |
|---|---:|---|
| Controller + progress state restore | PASS | cursor=1, step=1, family count=1, streak=1, evaluations=1 exactly restored |
| Resumed threshold continuation | PASS | resumed run reaches one NO_PROGRESS at the same remaining window, then REPLAN and completion |
| Progress policy drift | PASS | changed threshold descriptor rejected by resume provenance |

### Boundary probe — `stage6_progress_boundary_probe.py`

| Scenario | Result | Important observation |
|---|---:|---|
| Verified fact metadata churn | PASS | evidence-ref change alone does not change progress fact hash |
| Whitespace-sensitive verified value | PASS | meaningful string whitespace difference remains distinct |
| Global no-progress repeat identity | PASS | repeat counts 1,2,3 across alternating families; recovery REPLAN, REPLAN, SWITCH_STRATEGY |
| Historical successful artifact tamper | PASS | terminal persistence recovery scheduled before next Actor; controller cursor does not advance |
| Evidence JSON boundary | PASS | mapping key order canonicalized; string whitespace preserved |

### Strategy probe — `stage6_progress_strategy_probe.py`

| Scenario | Result | Important observation |
|---|---:|---|
| Verified fact content change | PASS | `verified_fact_content_changed` recognized |
| Same evidence after strategy switch | PASS | switch resets local window but identical evidence remains non-novel |
| Progress after switch | PASS | last-progress generation becomes current generation |
| Strategy exhaustion | PASS | STRATEGY_EXHAUSTED routes to terminal ESCALATE |
| Recovery sample isolation | PASS | recovery transition leaves Actor progress evaluation count unchanged |
| Changing failed errors | PASS | two TOOL_ERRORs, zero progress events, no NO_PROGRESS supersession |

## Zero-tolerance counters

```text
Actor self-reported progress acceptances        0
cosmetic decision loop evasions                 0
specific-failure supersessions by NO_PROGRESS   0
artifact-tamper progress acceptances            0
historical-tamper Actor continuations           0
resume progress divergence                      0
policy-drift acceptances                        0
global repeat identity divergence               0
fact metadata false-progress cases              0
whitespace false-no-progress cases              0
recovery transitions counted as Actor samples   0
failed output progress acceptances              0
strategy exhaustion nonterminal cases           0
```

## Evidence limitations

This matrix does not claim semantic relevance of novel evidence. New canonical content, including timestamps/nonces/random values, can be syntactically novel while being strategically useless. The hard budget still bounds such execution. Semantic usefulness requires a later, separately scoped contract.
