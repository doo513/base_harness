# Stage 01 — Truth + Execution Integrity

Status: **HISTORICAL COMPLETE — canonical genealogy reconstructed retrospectively**

This directory is a retrospective genealogy package. It does not claim that a canonical Stage01 directory, contract, or independent Stage01 Git commit existed at the time of the original work.

## Surviving evidence

The archive index preserves these early harness artifacts:

- `verified_state_harness_v0_1.zip` — SHA-256 `ba6deadaa2be9b79ff1994260eb49835410e8d2384ce6afb6d473ab8f1dcebbf`;
- `verified_state_harness_v0_2_hardening.zip` — `ff9427ea2368b89a9381b456add1bbdba7985cd684f8d98cfb520598ce0cf2d7`.

The next indexed transition artifacts already point toward Stage02:

- `verified_state_harness_stage2_workpack.zip` — `100ec6676d7551a217ed012f89b15fa13c9d3ab83d7565eed81d0a4ebc34c78e`;
- `verified_state_harness_v0_3_stage2_rc1.zip` — `83c73bb3fca0543d1dba4c873bd2ac6a24ef4a43da45db2414a90ef823d7bd5c`;
- `verified_state_harness_handoff_pack_stage02_partial.zip` — `0e8c8dd94532d21cf5d2e2242487e94df01fc581e26c47232e806bfcbbbbf0ed`.

The current taxonomy labels Stage01 **Truth + execution integrity**. The association of `v0.1` and `v0.2 hardening` with Stage01 is retrospective sequencing/navigation. Because the original archive bytes are absent from this repo, their exact internal guarantees are not independently revalidated here.

## Git boundary

Surviving Git history contains no independent Stage01 commit between:

- initial commit `35cbce265852ce5cc689ad1b4cfde14e3fb76221`; and
- first explicit research-stage checkpoint `96a89afb5052ed116a2844e1e6215b7e03de533e` (`research(stage-02): close production sandbox isolation gate`).

Therefore the early v0.1/v0.2 lineage is preserved as archive provenance, not rewritten as Git-native Stage01 history.

## Historical-state preservation

The archive index explicitly warns that the Stage02 rc1/handoff lineage was PARTIAL / NOT EXITED at that point. This Stage01 reconstruction does not rewrite that later historical state. Current Stage02 PASS comes from subsequent Git-native direct runtime evidence.

## Canonical role now

This directory closes the missing **documentation/genealogy** link only. It does not add new truth/execution-integrity mechanism evidence.

See:

- [`RETROSPECTIVE_PROVENANCE.md`](./RETROSPECTIVE_PROVENANCE.md)
- [`EVIDENCE_INDEX.md`](./EVIDENCE_INDEX.md)
- `docs/archive/ARTIFACT_INDEX.md`
