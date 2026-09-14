# Domain Policy and Evidence Boundary Implementation

## Situation

The previous structure kept domain behavior in the Kernel and exposed overlapping domain and skill choices in the TUI. Verification criteria were also not represented as a domain-owned contract, so adding a new domain would require changing common orchestration code.

## Reason

Domain-specific guidance should be replaceable without weakening the Kernel's common safety and completion rules. Measurement must remain an observation supplied to the verifier, not an LLM-generated approval or a Ready authority.

## Action

- Added `@base-harness/domain` as a workspace package.
- Added file-backed `SKILL.md` and `spec.json` resources for `develop`, `general`, and `hackathon`.
- Moved domain/skill compatibility and policy composition into the domain package.
- Removed the Kernel's direct `general` permission branch and `hackathon` planning branch; Host now supplies the resolved policy.
- Made Host apply the same normalized domain/skill selection used by the TUI preview.
- Made persisted session selection validation call the same domain policy resolver instead of enumerating domain and skill names.
- Added domain verification and measurement requirements to the Host status policy.
- Added `EvidenceSummary` creation and compact one-line serialization for action- and criterion-bound observations.
- Coordinator forwards host-produced `evidenceSummary` metadata, and the sidecar validates its action, criterion, status, and domain-required fields before recording it.
- Kept Candidate, Overlay, verifier attestation, repair, and root-only Ready authority outside the measurement helper.

## Result

Domain policy is now selected and composed by Host from resource files, while Kernel remains responsible for generic planning and admission decisions. The TUI domain selector no longer presents `hackathon` as a separate domain; the skill remains available through the dedicated control path.

The evidence helper can produce a small `evidence-summary-v1` record containing run, scope, action, criterion, status, observed values, and an artifact or detail reference. The sidecar records a supplied summary only after binding checks; the summary deliberately cannot create Evidence approval or Ready state.

## Evidence

- `runtime/packages/domain/src/index.ts`
- `runtime/packages/domain/src/measurement.ts`
- `runtime/packages/domain/resources/develop/spec.json`
- `runtime/packages/domain/resources/general/spec.json`
- `runtime/packages/domain/resources/hackathon/spec.json`
- `runtime/packages/kernel/src/index.ts`
- `runtime/packages/kernel-host/src/index.ts`
- `runtime/packages/tui/src/component/dialog-agent.tsx`
- `runtime/packages/tui/src/harness/pending-control.ts`

No automated test or typecheck result is asserted in this report; validation remains a separate step.

## Residual Risk

- Summary emission remains producer-driven: tools that do not provide `evidenceSummary` still rely on the existing action observation path, so domain policy does not silently invent measurements.
- `SKILL.md` resources are stored with each domain but are not yet a fully versioned prompt-loading protocol.
- A compact summary reduces context cost but does not by itself prove causality, independence, or final correctness; those remain verifier and external-oracle responsibilities.
- Domain and skill identifiers remain in the compatibility-facing Kernel types for this transition; the policy logic, rather than the public type aliases, is now domain-owned.
