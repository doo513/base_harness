# Remediation — Stage00 Canonical Genealogy

Finding: `O00-001`  
Status: **CLOSED — documentation/genealogy only**

## Finding

Current canonical `docs/stages/` began at later Stages, while Stage00 was marked COMPLETE in the root status table. Historical provenance therefore existed but was not navigable through the canonical Stage structure.

## Evidence

- Git history begins at `35cbce265852ce5cc689ad1b4cfde14e3fb76221` and contains no independent Stage00 commit before the first explicit Stage02 research checkpoint `96a89afb5052ed116a2844e1e6215b7e03de533e`.
- `docs/archive/ARTIFACT_INDEX.md` preserves filenames and SHA-256 values for research/workpack artifacts, but not their bytes.

## Action

Created `docs/stages/stage-00-research-contracts/` as a retrospective provenance package with:

- explicit Git boundary;
- archive SHA index;
- confidence/uncertainty rules;
- prohibition on inventing a historical `CONTRACT.md` or missing contents.

## Validation rule

Closure means only that the genealogy gap is now canonical and traceable. It does **not** create new Stage00 semantic/mechanism evidence.

## Residual

Original archive contents cannot be independently re-read from the current repository. Their exact internal claims remain unknown unless the original bytes are recovered separately and match the preserved SHA-256 values.
