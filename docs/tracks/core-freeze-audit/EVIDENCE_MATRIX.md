# Core Freeze Evidence Matrix

Validated implementation: `abed36ae430d0aa11711da267750847f792d61b6`  
CI: `31959676893` — SUCCESS  
Regression: `209 passed, 5 skipped`

| Claim / finding | Classification | Evidence method | Result | Status |
|---|---|---|---|---|
| Stage08 verified-read returns the bytes it hashes | RESOLVED | `storage.py` source + single-buffer artifact integrity probe | swap-after-read/tamper/missing/path escape all blocked | PASS |
| nested RO descendant cannot silently inherit false RO guarantee | RESOLVED | namespace config source + raw mount attack + fail-closed topology probe | raw descendant writable semantics reproduced; harness rejects topology | PASS in supported fail-closed policy |
| attested backend owns actual strict side-effect execution | RESOLVED | `tools.py` source + backend binding attack probe | unsafe handler calls 0; valid path one attestation/one execution | PASS |
| claim class determines allowed verifier/contract | CONFIRMED | claim registry + Software profile + Stage04 probes | unknown semantic class fail-closed | PASS |
| repository-style Software build/test/behavior verifier matrix | SUPPORTED | executed 17-case benchmark | FP=0, FN=0 on frozen corpus | PASS for corpus; not broad real-world accuracy |
| controlled typed Recovery has causal utility | SUPPORTED | matched deterministic A/B | recoverable 3/3 vs baseline 0/3; safety regressions 0 | PASS for controlled benchmark |
| activity novelty is not progress | RESOLVED | Stage06 progress/adversarial probes | volatile output progress events 0 | PASS |
| explicit task progress is monotonic and profile-owned | CONFIRMED | task-world progress probe | milestone removal/score regression credit 0 | PASS for framework |
| trusted fact projection is bounded | RESOLVED | Stage07 growth + cost probes | 200 raw facts ~1,037,090 chars vs bounded full context 7,660 chars | PASS |
| GoalContract silently truncates mandatory semantics | RESOLVED by fail-closed policy | GoalContract source + bounds probe | oversized goal/criterion/flood rejected before run | PASS |
| retrieval can promote itself to fact/completion/progress | RESOLVED | Stage08 base/adversarial/resume probes | fact/completion mutation 0, retrieval false-progress 0 | PASS |
| ref-string novelty was sufficient to reopen refuted hypothesis | CONFIRMED DEFECT at pre-audit head | source inspection + same bytes/different basename reproduction | refs differed for same bytes | FIXED |
| same bytes under new ref can reopen after fix | RESOLVED | Core Freeze direct probe | `same_content_new_ref_not_novel=true` | PASS |
| actual content delta can reopen | CONFIRMED | Core Freeze direct probe | changed bytes from stable source admitted as novel | PASS |
| verified same-key fact could leave stale refuted marker | CONFIRMED DEFECT at pre-audit head | `HarnessState.commit_verified` source + direct state transition | stale current marker possible | FIXED |
| verified same-key fact clears current refuted marker after fix | RESOLVED | Core Freeze probe | current fact exists, refuted marker absent | PASS |
| large structured Observation duplicated raw payload in durable state | CONFIRMED DEFECT at pre-audit head | `_store_tool_observation` source + large nested output | dict/list bypassed string-only truncation | FIXED |
| full raw tool output remains available after durable preview bounding | CONFIRMED | artifact integrity read in new unit/probe | artifact exact output/error retained | PASS |
| durable structured preview reduction | CONFIRMED cost proxy | Core Freeze probe | 40,073 → 2,861 serialized chars; 92.8605% reduction | PASS |
| artifact integrity is re-read by multiple verifiers in one attempt | SUPPORTED operational debt | `EvidenceRefVerifier` + Software execution verifier source | same evidence can be verified twice | CONDITIONAL optimization |
| Stage02 independent clean-host reproduction exists | GAP | evidence inventory | current hosted/internal CI only | OPEN |
| all official benchmark runs have immutable image/VM identity | GAP | provenance source | identity captured when available but not official-profile mandatory | OPEN |
| Software security-property verifier exists | GAP | Software registry source | unregistered | OPEN |
| CTF exploit/service/remote semantic verifier exists | GAP | CTF profile source | structural supported-only intermediate | OPEN |
| real stochastic LLM Recovery benefit is proven | GAP | benchmark inventory | controlled deterministic A/B only | OPEN |
| shipped domain profiles define task milestones | GAP | DomainProfile hook + profiles | framework exists; domain definitions incomplete | OPEN |
| >64K contract support is required by current workload | GAP / no evidence | workload evidence inventory | no demonstrated blocker | DEFER |
| safe global orphan GC is required for correctness | NOT NEEDED for correctness | retrieval transaction design | orphan blobs non-authoritative | CONDITIONAL ops |
| remote provider honesty/replay proof required now | NOT NEEDED for shipped scope | current local lexical provider | no remote provider shipped | CONDITIONAL |

## CI gate inventory at freeze candidate

The successful workflow ran:

- Full pytest regression
- Core Freeze audit regression probe
- Stage03 resume
- Stage04 semantic + repository execution benchmark
- Stage05 base/adversarial/terminal/crash/strategy + A/B effectiveness
- Stage06 base/adversarial/resume/boundary/strategy/task-world
- Stage07 base/adversarial/resume/compat/growth/cost/mandatory-goal
- Stage08 retrieval base/adversarial/resume/cost + single-buffer artifact integrity
- Stage02 nested mount/topology cost/backend binding/backend cost

## Evidence interpretation boundary

Internal CI demonstrates repeatability on the recorded GitHub hosted environment. It is **not** counted as independent clean-host reproduction. Likewise 0 FP/FN on the frozen Stage04 corpus is not generalized to arbitrary repositories/CTF tasks.
