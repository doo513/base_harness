# Commit / Versioning Policy

Working/research branches may be named by stage; this delivery uses `research/verified-state-stage02-rc2`.

Version mapping:
```text
v0.1.0      initial verified-state baseline
v0.2.0      Stage 01 truth/execution hardening
v0.3.0-rc1  Stage 02 partial capability isolation
v0.3.0-rc2  Stage 02 production-sandbox/evidence candidate
v0.3.0      Stage 02 PASS only
v0.4.0      Stage 03 resume/reproducibility
v0.5.0      Stage 04 semantic verification
v0.6.0      Stage 05 failure recovery
v1.0.0      core gates + cross-domain validation complete
```

Commit pattern: `research(stage-02): ...`, `test(stage-02): ...`, `fix(stage-02): ...`, `docs(stage-02): ...`.

Do not tag a stable version while its stage is PARTIAL. This branch records code version `0.3.0`, but no Git tag is created unless explicitly requested.
