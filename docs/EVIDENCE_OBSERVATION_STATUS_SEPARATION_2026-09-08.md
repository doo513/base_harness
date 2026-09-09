# Observation Verdict and Historical Case Status Separation

Date: 2026-09-08
Status: Implemented; local repair diagnostic and three typechecks passed. Python regression gate remains failed due to one newly authored fixture setup error.

## Situation

The previous local-repair run produced correct final file contents, but root Ready selected evidence families labelled disputed. Source analysis located the mismatch in VerificationEngine._verify_claim: family.status was copied from the whole EvidenceMemory case, while claim acceptance used current verifier observations.

EvidenceMemory retains prior soft failures for a claim case. Corrected candidate revisions therefore inherit a disputed historical case even when their current content predicates pass. A second issue was append-only family metadata: later observations of the same command/cwd family could leave its earlier status and claim association in the displayed list.

The current acceptance code also allowed a passing verifier to satisfy the claim despite another current verifier returning a soft counterexample. Historical disputed cases were allowed to supply additional independent methods.

## Reason

A historical case warning, a current failed observation and unresolved simultaneous counterevidence are different facts. They must not be represented as one overloaded status.

Current independently checked corrected content may be accepted without deleting prior failures. Actual counterevidence from the current verification must still prevent Ready. Historical disputed cases must not fill a missing independence requirement.

## Action

Changed five files:
- src/harness/verification_v2.py
- runtime/packages/verification/src/types.ts
- tests/test_restored_verification_boundary.py
- tests/test_verified_sidecar.py
- runtime/script/verify-provider-public-boundary.mjs

Family status now describes its latest recorded verification observation. New optional statusScope=verification_observation explicitly distinguishes this from legacy status semantics. Historical state remains in memoryCaseStatus; the existing trustTier remains a memory tier.

Family records link current evidenceIds and, when available, candidateId, candidateRevision and patchHash. Records are updated by (familyId, claimId), preserving distinct claim associations for a shared method without treating them as independent methods.

Prior claim_evidence artifacts and memory contradictions are retained. A later corrected observation updates the live family summary instead of rewriting those immutable artifacts.

If current verification has both passing and failing observations, the claim is refuted rather than accepted on the passing subset. Current families are disputed, and the existing rejection path handles the failed criterion.

Historical independence is now available only from active cases. Existing freshness, applicability and verifier-revocation checks remain. Hard-contradiction and revoked-dependency quarantine behavior is unchanged.

The local-repair diagnostic now inspects stored root Ready, checks selected family status and evidence links, and requires the historical soft-failure warning to remain present. Bounded artifact inspection is shared with the provider-failure diagnostic.

Protocol v4 and the existing artifact schema version are unchanged. New TypeScript metadata fields are optional for stored-artifact compatibility. Legacy artifacts are not rewritten and lack the new statusScope discriminator.

## Result

| Gate | Result |
| --- | --- |
| Selected Python verifier regression | 64 passed, 1 failed |
| Verification typecheck | Passed |
| Coordinator typecheck | Passed |
| Host typecheck | Passed |
| Real Host/headless local repair and stored Ready-family checks | Passed |
| Combined gate command | Exit 1; not promotion-ready |
| Full repository suite / cross-platform tests | Not run |

The real fixture repaired only unit-0 in its original child session, retained fixture-reasoner/high, and did not restart unit-1 or the whole plan. The rejected content was absent from the base target at the pre-repair observation point. Final files matched expected bytes.

Stored root Ready selected active observation families. The selected repaired claim's family retained memoryCaseStatus=disputed, preserving its historical failure warning. This addresses the specific phase44 metadata mismatch in a fresh run; it does not repair or reinterpret old artifacts.

The actual client exited 0. The diagnostic intentionally stopped the Host, which exited 143. The combined command exited 1 because of the Python test failure.

## Evidence

- Gate log: .tools/validation/restoration-phase45-evidence-status-gates.log
- Diagnostic result: .tools/validation/restoration-phase45-evidence-status.result.json
- Session: ses_f814cef63ffe8xT1r7M1mWpni9
- Run: run-37861e3d-0050-4bd8-b781-9b9ed29251b6
- Stored root Ready: C:/Users/doo33/AppData/Local/Temp/base-harness-real-host-vowCFX/state/base-harness/runs/afed4115d52c8628-aca81fe2/artifacts/f8/f8d148c40a732f8eb95832c37f1ebbd01709c8616dd6af0ed05ca89a4c9c10c5.json
- Companion record: docs/evidence/EVIDENCE_OBSERVATION_STATUS_SEPARATION_2026-09-08.json
- Prior finding: docs/WORKER_LOCAL_REPAIR_AND_EVIDENCE_LINEAGE_2026-09-08.md

The first patch application failed because the shell text read included an extra terminal newline. A conflict-only reread confirmed the source was unchanged apart from that transport newline; a narrower application succeeded. No unexpected external edits were found in that conflict check.

## Failed Test and Pending Decision

The new test test_disputed_history_cannot_supply_missing_independence fails at tests/test_verified_sidecar.py:907, before reaching its disputed-case assertion.

The test uses an execution verifier without freshnessSeconds, then incorrectly expects its active historical evidence to be reusable. Existing policy correctly excludes execution history without a freshness bound. This is a setup error in the newly authored test, not evidence that the new production exclusion failed.

The proposed correction is to set a positive freshness_seconds on that test's verifier, then rerun the affected test and regression gate. The user has been asked; this report does not claim the correction was authorized or applied. The failing test was left unchanged.

The other three added regression tests passed: repaired-observation versus disputed-case separation, per-claim association of a shared family, and rejection of simultaneous soft counterevidence.

## Residual Risk

These are same-agent-authored tests and a scripted local provider, not independent user validation. One regression gate is explicitly incomplete.

Historical hard contradictions still quarantine a case across later attempts. Broader supersession rules, revision-aware case identity and verifier-revision trust are not redesigned here. Old soft failures remain advisory case warnings rather than being automatically erased or declared resolved.

Current conflicting observations use the existing implementation rejection/repair route. A domain-specific method for distinguishing faulty verification from an implementation defect remains a separate concern.

The shared-family representation can contain multiple claim association rows with the same familyId. Consumers must count independent methods/families, not raw rows. The acceptance algorithm continues to count method identities.

No actual OAuth, prolonged session, complex multi-file repair, repeated-repair exhaustion, live TUI or complete platform regression was exercised. The provider-failure branch was not rerun after factoring its artifact-inspection helper.

No commits, Git commands or push occurred; net_monitor.py was untouched. Earlier phase38 and phase40 diagnostic issues remain unchanged. This report and its companion JSON are engineering records, not additional Harness Evidence or Ready.
