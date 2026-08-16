# Stage 04 Evidence Matrix

Evidence grade used here:

```text
A = direct code/runtime/CI evidence
B = primary external evidence
C = synthesis/design inference
```

| Requirement | Mechanism | Test / Evidence | Result | Grade |
|---|---|---|---|---|
| result cannot self-inflate level | `VerifierChain._normalize` | inflation test + direct probe | PASS | A |
| result cannot invent coverage | configured `covers` normalization | coverage spoof test | PASS | A |
| domain declares minimum semantics | `VerificationContract` | profile contract tests | PASS | A |
| semantic evidence required | `require_evidence` | evidence-free result test | PASS | A |
| artifact bytes match content-address ref | read-time SHA-256 | tamper unit/probe | PASS | A |
| free-form generic claims rejected | structured verifier type gate | unit/probe | PASS | A |
| missing/wrong JSON path rejected | explicit resolver | unit/probe | PASS | A |
| generic assertion cannot rename itself into domain semantics | `artifact_assertion.*` namespace | masquerade unit/probe | PASS | A |
| structural evidence not mislabeled execution truth | `Authority.SUPPORTED` | runtime test | PASS | A |
| execution assertion can commit when contract satisfied | structured assertion + runtime | runtime integration test | PASS | A |
| contract survives resume fingerprint | manifest config descriptor | manifest test | PASS | A |
| harness version drift blocked | resume version guard | version provenance test | PASS | A |
| synthetic semantic FP | adversarial matrix | 0 | PASS | A |
| synthetic semantic FN | adversarial matrix | 0 | PASS | A |
| full regression | GitHub Actions run 31934328945 | 69 passed / 5 skipped | PASS | A |

## Environment-dependent Stage 02 note

The five skipped tests include live namespace-sandbox tests that skip if the CI host cannot produce a `runtime_probe` attestation. They are not counted as production sandbox proof. Stage 02's prior direct runtime evidence remains the production isolation evidence, and the Stage 02 namespace implementation was not changed by Stage 04.
