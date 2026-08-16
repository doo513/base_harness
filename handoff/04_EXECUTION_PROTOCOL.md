# 04 — Execution Protocol

1. Inspect code/current stage/evidence/blockers/tests before modifying.
2. Freeze stage contract: Goal, Non-goals, Entry, Exit criteria, Threats, Tests, Artifacts.
3. Build unit + adversarial + integration + regression tests; security boundaries require attack probes.
4. Implement minimum necessary change; prefer explicit/fail-closed/single-state/deterministic design.
5. Run targeted, adversarial, full regression, compile/static, CLI smoke, environment probes.
6. Logic re-review: original failure solved? bypass? verifier independence? oracle mutability? evidence sufficiency? new source of truth? prior invariant weakened?
7. Freeze raw evidence, including failures, hashes/manifests/environment.
8. Write detailed stage report: objective, implementation, evidence, failures, corrections, risks, PASS/PARTIAL/FAIL, next allowed step.
9. Stop at stage boundary. Any failed exit criterion => PARTIAL/FAIL and no next stage.
