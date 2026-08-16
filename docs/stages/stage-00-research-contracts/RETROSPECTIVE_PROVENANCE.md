# Stage 00 Retrospective Provenance

## Reconstruction method

The reconstruction uses only two repository-native evidence classes:

1. Git objects/commit history that are still independently addressable;
2. `docs/archive/ARTIFACT_INDEX.md`, which preserves historical artifact filenames and SHA-256 values.

Missing archived ZIP/Markdown contents are not inferred.

## Git boundary

| Object | Evidence | Interpretation |
|---|---|---|
| initial repository | `35cbce265852ce5cc689ad1b4cfde14e3fb76221` | first surviving Git commit |
| initial tree | `bc2aa1f66ff8c14c8020ce2a85606add06a9630d` | preserved legacy tree |
| first Git-native research Stage checkpoint | `96a89afb5052ed116a2844e1e6215b7e03de533e` | Stage02 checkpoint; no independent Stage00/01 Git commits precede it |

Therefore Stage00 genealogy before Stage02 is archive-index provenance, not a recoverable commit-by-commit implementation history.

## Retrospective classification rule

The modern label `Research / contracts` is applied only as a navigation taxonomy. A historical artifact is listed as Stage00-adjacent when its preserved name identifies it as research/workpack/branch-preparation material. This is not equivalent to proving the artifact's internal semantic content.

## Confidence levels

- **High**: commit SHA/tree SHA, filename, recorded SHA-256, current taxonomy.
- **Medium**: artifact sequencing/role inferred directly from descriptive filenames.
- **Unknown**: exact internal claims, tests, contract wording, or implementation details of archive artifacts whose bytes are absent.

## Result

Canonical genealogy is reconstructed with explicit uncertainty. Historical mechanism claims remain bounded by later Git-native evidence rather than being backfilled into Stage00.
