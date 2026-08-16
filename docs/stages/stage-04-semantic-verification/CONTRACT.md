# Stage 04 Semantic Verification Contract

Status: **FROZEN FOR v0.5.0-rc1**

## Purpose

Stage 04 closes the gap between:

```text
only the verifier may commit
```

and:

```text
only an admissible, sufficiently strong verifier may commit this class of claim
```

The kernel must not treat a boolean return value, a stored artifact reference, or a verifier-provided level string as semantic truth by itself.

## Kernel requirements

1. A verifier result cannot report a verification level different from the verifier implementation's configured level.
2. Verification coverage is taken from trusted verifier configuration, not from result/candidate data.
3. Domain Profiles provide an explicit `VerificationContract`.
4. A contract may require named coverage, minimum strength, attached evidence, and minimum confidence.
5. State commit occurs only when the complete contract assessment passes.
6. Verification contract and verifier metadata are included in the reproducibility manifest fingerprint.
7. Structural/logical support does not receive `TRUSTED_TOOL` semantic authority; it is recorded as `SUPPORTED`.

## Generic semantic primitive

The kernel provides one deliberately narrow execution verifier:

```json
{
  "kind": "artifact_json_assertion",
  "path": ["output", "returncode"],
  "operator": "eq",
  "expected": 0
}
```

It proves only that one stored JSON evidence artifact equals the expected value at the declared path. It does **not** infer the truth of arbitrary free-form natural-language claims.

Domain-specific semantics must be implemented by a Domain Profile verifier whose declared coverage satisfies that profile's contract.

## Adversarial matrix

Required negative cases:

- result-level inflation
- result-supplied coverage spoof
- evidence-free high-level boolean success
- free-form claim presented to the generic semantic verifier
- wrong expected value
- missing artifact path
- unsupported operator
- unresolved/multiple evidence refs

Required positive cases:

- nested dict equality
- list-index equality
- boolean equality
- software runtime claim commit with execution evidence

## Exit criteria

```text
Stage 04 dedicated tests: PASS
full regression: PASS
synthetic verifier FP: 0
synthetic verifier FN: 0
level inflation attack: blocked
contract fingerprint persisted: PASS
Stage 01–03 tests: no regression
```

This Stage does not claim that generic natural-language truth is solved. Its guarantee is that semantic authority is explicit, contract-bound, evidence-bound, and cannot be self-promoted by a verifier result object.
