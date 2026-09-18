---
name: goal-contract-authoring
description: Interpret a user request and draft a GoalContract with observable criteria, bound claims, explicit sources, and unresolved decisions.
---

# Author a GoalContract

Read the original request and the available workspace observations. Separate the requested result, scope, constraints, and verification needs. Preserve explicit requirements when choosing an implementation approach.

Write each required result as an observable criterion. Link it in both directions to the claims that establish it. Give different requirements distinct IDs even when their wording is similar. Keep optional improvements separate from mandatory success criteria. A claim should identify its target, capability, predicate, applicability, and required verifier strength. Use the supplied schema and registered verifier capabilities; an invented verifier or predicate is not a verification plan.

Distinguish what the user said, what a tool observed, and what you inferred. In interpretation records, cite the source and a useful pointer or short quote. A source label supplied by the model is a proposed attribution, not a recorded user response. A Host-provided clarification belongs to the question and candidate revision shown with it; use it to draft the next candidate without treating its wording as permission to execute.

Record uncertain choices explicitly. Implementation details that leave the requested result and scope unchanged can be assumptions. Missing user preferences, required values, conflicting requirements, scope changes, security choices, external effects, and unresolved verifier applicability should describe the decision and the affected claim or criterion IDs. Explain the plausible alternatives and suggest a resolution when the request supports one. Do not delete an uncertainty merely to make the contract pass.

Before submitting, compare the proposed criteria against the original request for omissions and contradictions. Submit the complete candidate in the supplied protocol. A reviewer correction or user clarification requires a new complete candidate; contract acceptance and execution permissions come from the Host and Runtime.
