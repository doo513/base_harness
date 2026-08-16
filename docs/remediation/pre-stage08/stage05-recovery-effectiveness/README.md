# Stage05 Recovery Effectiveness Remediation

Finding: `O05-001`  
Status: **CONTRACT FROZEN / benchmark implementation pending**

Stage05 already proves durable recovery-control mechanics, fail-closed unsafe retry behavior and resume ordering. This remediation measures a different question: whether those controls produce better task outcomes on matched failure-injection tasks.

The benchmark must not modify production recovery semantics to manufacture a positive result. It compares the existing `FailureRouter` with a conservative no-recovery baseline on identical tasks/controllers/oracles/budgets.

See [`CONTRACT.md`](./CONTRACT.md).
