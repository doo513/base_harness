# Stage05 Recovery Effectiveness Remediation

Finding: `O05-001`  
Status: **PARTIAL — controlled deterministic A/B effectiveness demonstrated; broad real-world effectiveness remains open**

Contract: [`CONTRACT.md`](./CONTRACT.md)

## Result

A matched deterministic benchmark compared the production `FailureRouter` against a conservative no-automatic-recovery baseline. The same controller, tools, oracle, budget and failure injection were used in each pair; only routing policy differed.

CI run `31955531150` on commit `1b8496c120f52496d53de90ef7aae013cc926962` produced:

- recoverable scenarios: `3`;
- Recovery completion rate: `1.0` (3/3);
- no-recovery completion rate: `0.0` (0/3);
- completion-rate delta: `+1.0`;
- recovered pairs: `tool_repair`, `missing_info_observe`, `verification_replan`;
- additional steps per recovered success: `2.3333333333333335`;
- additional tool calls per recovered success: `1.3333333333333333`;
- terminal safety regressions: `0`;
- unsafe retries: `0`;
- direct recovery verified-fact mutations: `0`;
- full regression: `182 passed / 5 skipped`;
- all Stage03–08 and Stage02 remediation gates: PASS.

## Interpretation

This closes the narrower question: **the existing recovery-control mechanism has demonstrated positive causal utility on the frozen deterministic failure-injection benchmark.**

It does not prove that Recovery improves arbitrary LLM agents, real repositories, CTFs, or natural task corpora. `O05-001` therefore remains PARTIAL rather than CLOSED.

## Reports

- [`BENCHMARK_REPORT.md`](./BENCHMARK_REPORT.md)
- [`EVIDENCE_MATRIX.md`](./EVIDENCE_MATRIX.md)
- [`COST_REPORT.md`](./COST_REPORT.md)
- [`FINAL_REREVIEW.md`](./FINAL_REREVIEW.md)
