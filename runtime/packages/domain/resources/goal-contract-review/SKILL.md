---
name: goal-contract-review
description: Review a proposed GoalContract against its original request for omissions, contradictions, scope, and verifiability; propose corrections or necessary user questions.
---

# Review a GoalContract

Compare the full candidate with the original request, cited observations, and Host-provided clarification context. Check whether every required result has an observable criterion and claims that can actually establish it. Check scope, exclusions, constraints, applicability, and the suitability of the proposed verification. Similar wording is not evidence that two requirements are equivalent.

Separate a correctable drafting defect from a missing user decision. Use `revise` for an omission, contradiction, or inadequate verification description that can be corrected from the available request and observations. When supplying a correction, return the complete revised candidate, including its interpretation records. Do not silently invent requirements or represent an inference as a user answer.

Use `needs_input` when a consequential choice requires the user's missing preference or decision. State the decision clearly, identify the affected IDs, cite the supporting source, and suggest a resolution when justified. Minor implementation choices can remain warning-level assumptions. Ask about the actual unresolved choice rather than asking the user to approve a structural error or a service failure.

Use `pass` only when no blocking issue remains. A pass says that the candidate is semantically adequate for the supplied request; it does not attest that the work has been executed or verified. Keep Evidence, Ready, tool permissions, and Runtime acceptance outside this review. Follow the response schema supplied with the request.
