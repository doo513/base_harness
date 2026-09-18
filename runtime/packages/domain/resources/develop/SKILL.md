---
name: domain-develop
description: Contract-scoped development, Candidate changes, and verification handoff.
---

# Develop execution context

Inspect the existing implementation and preserve unrelated user changes. Connect each proposed change to the accepted GoalContract's claims and criteria. Keep direct work within the accepted scope; when using a WorkGraph, make dependencies and read/write paths explicit.

Implement assigned WorkUnits through the existing tools and Candidate transaction. A worker owns only its declared write paths. Report the resulting files, the checks actually run, and any remaining integration requirement so the Coordinator can continue its established lifecycle.

Use the current runtime and available dependencies. Do not expand permissions, bypass sandbox restrictions, or infer acceptance from this document. Code, test output, and model summaries remain candidate data until the Python verifier establishes Evidence and Ready.
