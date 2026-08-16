# Stage 04 — Semantic Verification

Status: **PASS / EXITED — v0.5.0**.

## Result

Stage 04 establishes an explicit semantic-authority contract between Domain Profiles and the Kernel.

```text
configured verifier declaration
→ normalized strength + coverage
→ integrity-verified evidence
→ Domain VerificationContract
→ Kernel commit / fail-closed rejection
```

Implemented protections:

- verifier result level inflation blocked;
- result coverage spoof blocked;
- evidence/strength/coverage requirements first-class;
- content-address artifact integrity checked on semantic read;
- generic structured assertion restricted to `artifact_assertion.*`;
- domain-semantic fact names require domain-specific verifier coverage;
- structural/logical facts use `SUPPORTED` authority;
- contract/verifier metadata fingerprinted for resume/reproducibility;
- harness-version mismatch blocks resume.

Promotion candidate `v0.5.0-rc3` passed 69 tests with 5 environment-dependent skips and an 8-case semantic probe with FP=0/FN=0.

Detailed artifacts:

- `CONTRACT.md`
- `../../STAGE4_IMPLEMENTATION_REPORT.md`
- `../../STAGE4_FINAL_REREVIEW.md`
- `../../STAGE4_EXIT_DECISION.md`
- `../../STAGE4_EVIDENCE_MATRIX.md`
- `../../../evidence/stage4_validation_summary.json`

## Non-claim

Stage 04 does not solve arbitrary natural-language truth. The generic verifier proves narrow structured propositions over stored artifacts; domain meaning remains a Domain Profile responsibility.

## Next

Stage 05 — Failure Recovery.
