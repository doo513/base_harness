# Evidence Memory Lifecycle v2

Status: **IMPLEMENTED / VALIDATION PENDING**

## Contract

This extension adds lifecycle and retrieval structure around cross-run experience without changing the frozen Verified-State Kernel boundary.

```text
immutable Evidence references
-> append-only Experience events
-> derived Case trust profile
-> derived trust tier
-> title-based Markdown projection
-> Stage-08 untrusted retrieval
-> verification candidate only
```

The following invariants are mandatory:

1. Historical material never becomes a current trusted fact or completion proof.
2. Raw Evidence references and Experience events are immutable; only the derived Case view changes.
3. Promotion counts unique content-addressed Evidence families, not retrieval, wording, or repeated publication.
4. Hard contradiction quarantines a Case; soft contradictions demote it by policy.
5. Environment mismatch is `not_applicable`, not a contradiction.
6. Non-use does not demote a Case; age marks it stale and lowers its retrieval value.
7. GoalContract, verifier, environment, run, and Evidence-family revisions remain attached to each event.
8. RAG is a disposable projection over the event ledger, not the source of truth.

## Trust pyramid

| Tier | Admission rule | Permitted effect |
| --- | --- | --- |
| `candidate` | No qualifying support family | Suggest a check only |
| `supported` | One independent support family | Recommend related verification |
| `reproduced` | Configured independent-family threshold | Raise verification priority |
| `robust` | Higher family threshold across configured environments | Default verification candidate |
| `quarantined` | Any unresolved hard contradiction | Counterexample/failure retrieval only |

No tier can replace direct evidence from the current run.

## Structured case candidate

The Actor may stage a case only through `memory_candidate.<label>` with schema `experience-case-candidate-v2`, registered Evidence references, SRARE fields, a stable domain, structured applicability, a recording class, and an event kind.

Publication eligibility is kernel-observable:

- `verified_success` requires accepted run completion.
- `critical_failure` requires a recorded run failure.
- contradiction events require a recorded refutation or failure.
- `not_applicable` records scope mismatch without changing trust rank.

## Persistence layout

```text
<memory-root>/<project-id>/
  items/                  legacy v1 JSON records
  experience-events/      immutable integrity-sealed event JSON
  experience-documents/   title-based Markdown projections by domain
```

Case IDs derive from project, kind, domain, claim, and applicability rather than titles. Titles are human-facing retrieval labels and may not act as identity.

## Known limitations

- Current Evidence lineage is conservatively approximated from content-addressed artifact roots.
- Verifier revisions are recorded for impact analysis, but revocation and automatic dependent-case recomputation are not yet exposed as an operator command.
- GoalContract revisions are bound to events, but acceptance-criterion-to-Evidence coverage remains a separate completion-verification concern.
- Applicability is structurally stored and retrieved, but current Stage-08 lexical requests do not yet provide a kernel-owned environment filter.
- This change has not run targeted, adversarial, regression, or prior-Stage validation gates in this implementation session.
