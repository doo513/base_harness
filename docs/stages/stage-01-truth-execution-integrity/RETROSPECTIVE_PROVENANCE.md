# Stage 01 Retrospective Provenance

## Reconstruction rule

Only surviving Git objects and the preserved archive index are authoritative for this reconstruction. Descriptive filenames may establish an ordering/role hypothesis, but absent ZIP contents are not reconstructed.

## Early lineage

| Order | Historical identifier | Preserved SHA-256 / Git SHA | Retrospective interpretation |
|---:|---|---|---|
| 1 | `verified_state_harness_v0_1.zip` | `ba6deadaa2be9b79ff1994260eb49835410e8d2384ce6afb6d473ab8f1dcebbf` | early verified-state harness lineage |
| 2 | `verified_state_harness_v0_2_hardening.zip` | `ff9427ea2368b89a9381b456add1bbdba7985cd684f8d98cfb520598ce0cf2d7` | later hardening lineage; exact changes unavailable |
| 3 | `verified_state_harness_stage2_workpack.zip` | `100ec6676d7551a217ed012f89b15fa13c9d3ab83d7565eed81d0a4ebc34c78e` | transition toward Stage02 |
| 4 | `verified_state_harness_v0_3_stage2_rc1.zip` | `83c73bb3fca0543d1dba4c873bd2ac6a24ef4a43da45db2414a90ef823d7bd5c` | Stage02 release-candidate-era artifact |
| 5 | `verified_state_harness_handoff_pack_stage02_partial.zip` | `0e8c8dd94532d21cf5d2e2242487e94df01fc581e26c47232e806bfcbbbbf0ed` | explicitly historical PARTIAL handoff |
| Git boundary | first explicit Stage commit | `96a89afb5052ed116a2844e1e6215b7e03de533e` | Stage02 closes production sandbox isolation gate in Git-native history |

## What is known vs unknown

Known:

- filenames;
- recorded SHA-256 values;
- current Stage taxonomy;
- Git commit/tree chronology;
- Stage02 partial history must remain partial at the historical point where it was recorded.

Unknown from the current repository alone:

- exact source tree inside v0.1/v0.2 archives;
- exact test counts/results inside those archives;
- exact historical contract text;
- whether the label Stage01 was used at the time.

## Result

The missing canonical link is restored without silently converting archive identity into semantic proof.
