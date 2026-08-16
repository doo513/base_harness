# Branch Plan

Target repository: `doo513/base_harness`

Delivery branch: `research/verified-state-stage02-rc2`

`main` remains the original Base Harness MVP. Verified-State implementation lives under `experimental/verified-state-harness/`; current control material lives under `handoff/`; stage research/evidence lives under `docs/verified-state/`.

Promotion flow:
```text
Stage implementation → targeted tests → adversarial/integration tests
→ full regression → logic/security/integrity re-review
→ evidence/report freeze → PASS/PARTIAL/FAIL → next stage only on PASS
```

Version history represented by the research artifacts:
```text
v0.1.0      initial verified-state baseline
v0.2.0      Stage 01 truth/execution hardening
v0.3.0-rc1  Stage 02 PARTIAL
v0.3.0-rc2  production sandbox + direct attack evidence candidate
v0.3.0      Stage 02 PASS criteria satisfied in this branch
```

No tag is created by this branch operation.
