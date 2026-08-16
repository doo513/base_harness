# Stage 04 Semantic Verification Contract

Status: **FROZEN FOR v0.5.0-rc3**

## Purpose

Stage 04 strengthens `only verifier may commit` into:

> **Only a configured, sufficiently strong, evidence-integrity-checked verifier satisfying the Domain Profile contract may commit that class of claim.**

The kernel must not treat a boolean return value, a stored artifact reference, a verifier-provided level string, or an arbitrary semantic claim key as truth by itself.

## Kernel requirements

1. A verifier result cannot report a level different from the verifier implementation's configured level.
2. Verification coverage comes from trusted verifier configuration, not result/candidate data.
3. Domain Profiles provide an explicit `VerificationContract`.
4. Contracts may require named coverage, minimum strength, evidence, and confidence.
5. Evidence artifacts used for semantic verification must pass their content-address SHA-256 check at read time.
6. Generic structured artifact assertions may commit only under `artifact_assertion.*`; arbitrary domain-semantic fact keys require a domain-specific verifier.
7. State commit occurs only when the complete contract passes.
8. Verification contract and verifier metadata are included in the reproducibility manifest fingerprint.
9. Structural/logical support is recorded with `SUPPORTED` authority rather than `TRUSTED_TOOL` semantic authority.
10. Resume must reject a persisted run whose `harness_version` differs from the currently executing harness.

## Generic semantic primitive

```json
{
  "kind": "artifact_json_assertion",
  "path": ["output", "returncode"],
  "operator": "eq",
  "expected": 0
}
```

It proves only that one integrity-verified stored JSON artifact equals the expected value at the declared path. It does not infer arbitrary natural-language truth.

## Adversarial matrix

Required negatives include:
- result-level inflation
- result-supplied coverage spoof
- evidence-free high-level success
- free-form semantic claim
- wrong expected value / missing path / unsupported operator
- artifact content tamper after creation
- generic assertion masquerading under an arbitrary domain-semantic key
- harness-version drift during resume

Required positives include nested dict equality, list-index equality, boolean equality, and an execution-level runtime commit in the reserved assertion namespace.

## Exit criteria

```text
Stage 04 dedicated tests: PASS
full regression: PASS
synthetic verifier FP: 0
synthetic verifier FN: 0
level inflation attack: blocked
artifact content tamper: blocked
semantic-key masquerade: blocked
harness-version drift resume: blocked
contract fingerprint persisted: PASS
Stage 01–03 tests: no regression
```

No claim is made that generic natural-language truth is solved. Domain semantic keys require domain-specific verifier code and coverage.
