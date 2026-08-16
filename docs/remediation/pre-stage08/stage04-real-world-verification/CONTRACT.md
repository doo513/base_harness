# Contract — Stage04 Execution-Semantic Claim Coverage

Status: **FROZEN before semantic implementation**

Findings: `O04-001`, `O04-002`

## Problem

The current Stage04 mechanism correctly blocks generic structured artifact assertions from authorizing arbitrary semantic claim keys. The SoftwareProfile, however, only registers `artifact_assertion.*`. Therefore the current 8/8 synthetic semantic matrix does not prove that real execution evidence can authorize domain claims such as build/test/behavior outcomes.

## Scope

Add narrowly typed Software claim classes backed by actual Harness tool-observation artifacts, then benchmark them on repository-style subprocess cases.

Initial claim classes:

1. `software.build_result` — key prefix `software.build_result.`;
2. `software.test_result` — key prefix `software.test_result.`;
3. `software.behavioral_acceptance` — key prefix `software.behavioral_acceptance.`.

`software.security_property` and CTF semantic classes remain out of this remediation unless separately contracted.

## Evidence schema

The verifier may consume only an integrity-verified Harness tool-observation JSON artifact with the existing runtime shape:

```json
{
  "ok": true,
  "output": {
    "returncode": 0,
    "stdout": "...",
    "stderr": "...",
    "timed_out": false
  },
  "error": null
}
```

The verifier must not trust a path reopen, free-form model text, an unregistered artifact, or a candidate-provided return code independent of evidence.

## Claim schemas

### Build / test

Candidate:

```json
{"succeeded": true}
```

For `succeeded=true`, acceptance requires all of:

- exactly one integrity-verified evidence artifact;
- artifact top-level `ok == true`;
- output object exists;
- `returncode == 0`;
- `timed_out == false`.

For `succeeded=false`, the verifier may establish an observed failed execution only when the artifact deterministically shows failure (`ok=false`, nonzero return code, or timeout). It must not infer why the build/test failed.

### Behavioral acceptance

Candidate:

```json
{"stdout_equals": "expected exact text"}
```

Acceptance requires successful, non-timed-out, zero-exit execution and exact stdout equality. No regex, substring, or model-semantic match in this contract.

## Authority

All three domain verifiers are `EXECUTION` level and may grant `ENVIRONMENT` authority only to their own registered key prefixes. They cannot authorize completion; Completion Oracle remains independent.

## Required adversarial cases

- success claim over nonzero return code -> reject;
- success claim over timeout -> reject;
- failure claim over successful execution -> reject;
- behavior claim with near-match/substring only -> reject;
- free-form candidate -> reject;
- evidence ref not present in Harness state -> reject;
- tampered artifact -> reject;
- generic artifact assertion under semantic Software key -> reject;
- semantic verifier under wrong claim prefix -> registry reject.

## Repository-style benchmark

Use real subprocess executions that create actual tool-observation artifacts, including at minimum:

- Python compile/build success and syntax-failure case;
- pytest test success and failing-test case;
- exact CLI/output behavioral success and near-match failure.

Gold labels must be defined before verifier prediction. Report TP/TN/FP/FN and preserve per-case evidence.

## Exit criteria

This remediation is PASS only if:

- all three claim classes are registry-bound to their dedicated verifier(s);
- unknown/wrong semantic classes fail closed;
- benchmark has at least 12 positive/negative/adversarial cases;
- false positives = 0;
- false negatives = 0 on the frozen corpus;
- artifact tamper and evidence-ref substitution fail closed;
- Stage03–08 and remediation regression gates remain green.

## Interpretation boundary

A PASS demonstrates typed execution-semantic verification on the frozen repository-style corpus. It does not prove universal software semantics, security properties, arbitrary build systems, or CTF semantic verification.
