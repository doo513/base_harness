# Stage 03 Evidence Matrix — v0.4.0

Evidence grades:

```text
A = direct implementation/runtime evidence
B = primary external evidence
C = design inference
```

| Requirement | Mechanism | Evidence | Result | Grade |
|---|---|---|---|---|
| public restore path | `HarnessRuntime.resume` | S3-12 + source | PASS | A |
| CLI restore path | `--resume` | S3-12 | PASS | A |
| stable run identity | persisted manifest run_id | forced-resume probe | PASS | A |
| atomic checkpoint replace | fsync temp → replace → dir fsync | source + corruption tests | PASS | A |
| checkpoint integrity | sealed envelope + state hash | S3-02 | PASS | A |
| checkpoint/event binding | event_seq + event_hash | S3-01/S3-03 | PASS | A |
| event tamper detection | seq/prev_hash/record_hash chain | S3-05 | PASS | A |
| event-ahead crash recovery | newer verified state.snapshot wins | S3-10 | PASS | A |
| checkpoint-ahead invalidity | anchor must exist in event ledger | S3-03 | PASS | A |
| canonical replay | validate every state.snapshot | S3-01 + direct probe | PASS | A |
| replay does not execute tools | replay only consumes event records | source review | PASS | A |
| non-idempotent action identity | H(run_id,step,tool,args) | receipt tests | PASS | A |
| committed action dedup | COMMITTED ToolResult replay | S3-07 | PASS | A |
| real forced kill resume | subprocess exit 73 | S3-09 + direct probe | PASS | A |
| duplicate external effects | receipt + restored step | direct probe | 0 duplicates | A |
| ambiguous side effect | PREPARED-only blocks execution | S3-08 + direct probe | PASS | A |
| task drift detection | manifest | S3-04 | PASS | A |
| budget drift detection | config fingerprint | S3-11 | PASS | A |
| verifier/profile drift coverage | class/source/config fingerprint | source + manifest | PASS | A |
| model-command drift coverage | adapter command SHA-256 | source + manifest | PASS | A |
| missing provenance behavior | warning / strict fail | S3-06 | PASS | A |
| wall budget continuity | persisted elapsed wall time | source + regression | PASS | A |
| dirty run-dir rejection | explicit new-run guard | S3-11 | PASS | A |
| Stage 01/02 regression | full pytest | 59 passed | PASS | A |
| Stage 02 isolation regression | real attack probe | 12+4 PASS | PASS | A |

## Evidence files

- `evidence/stage3_resume_probe.json`
- `evidence/stage3_pytest.txt`
- `evidence/stage3_full_pytest.txt`
- `evidence/stage3_compileall.txt`
- `evidence/stage3_stage2_regression_attack_probe.json`
- `evidence/stage3_manifest_example.json`
- `evidence/stage3_validation_summary.json`
- `evidence/stage3_source_hashes.json`
