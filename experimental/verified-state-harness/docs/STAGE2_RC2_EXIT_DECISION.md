# Stage 02 rc2 — Exit Decision

## Historical state

At handoff entry:

```text
Stage 02 = PARTIAL / NOT EXITED
First required task = Production Sandbox Backend + actual filesystem/network attack probe
```

That historical fact remains preserved in the archived handoff and rc1 artifacts.

## Exit matrix

| Exit requirement | rc1 | rc2 evidence | Decision |
|---|---|---|---|
| real productive filesystem boundary | BLOCKED | live namespace backend + positive control | PASS |
| outside read/write blocked | FAIL/NOT PROVEN | A01–A05 | PASS |
| Actor cannot read sealed assets | NOT PROVEN | A06 + integration | PASS |
| symlink escape blocked | NOT PROVEN | A07 | PASS |
| network deny | FAIL | A08/A09 | PASS |
| env sanitization | PASS | A10 regression | PASS |
| verifier candidate mutation blocked | NOT PROVEN | A11 + integration | PASS |
| oracle asset mutation blocked | integrity only | A12 + read-only mount + seal | PASS |
| strict backend evidence is real | partial | `source=runtime_probe` only | PASS |
| full regression | 40 pass | 47 pass | PASS |

## Additional defense-in-depth

The exit review also requires the four newly discovered channels to stay green:

```text
D13 read-only rootfs chmod escape
D14 nested userns remount
D15 workspace AF_UNIX host channel
D16 external hard-link inode escape
```

All are PASS in the recorded evidence.

## Decision

**PASS / EXITED** for Stage 02 under the declared Linux namespace threat model.

Version policy implication:

```text
v0.3.0-rc1 = Stage 02 partial
v0.3.0-rc2 = implementation/evidence candidate
v0.3.0     = allowed because Stage 02 gate is now satisfied
```

No Git tag is required by this report itself; repository tagging is a separate release operation.
