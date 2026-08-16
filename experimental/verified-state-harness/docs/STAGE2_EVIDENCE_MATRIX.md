# Stage 02 Evidence Matrix — rc2 Final

Evidence strength:

```text
A = direct implementation/runtime evidence
B = primary external evidence
C = synthesis/design inference
```

| Requirement | Mechanism | Direct test / probe | Result | Strength |
|---|---|---|---|---|
| Actor no state commit | CapabilityPolicy + detached state | regression | PASS | A |
| Verifier no Actor write capability | CapabilityPolicy | regression | PASS | A |
| run/oracle path topology | SecurityLayout | regression | PASS | A |
| local subprocess not miscalled sandbox | LocalProcessBackend negative attestation | regression | PASS | A |
| production attestation not spoofed | `runtime_probe` source requirement | strict runtime test | PASS | A |
| workspace usable | rw bind mount | positive control | PASS | A |
| traversal denied | chroot mount view | A01 | PASS | A |
| absolute outside read denied | unmounted host paths | A02 | PASS | A |
| absolute outside write denied | unmounted host paths | A03 | PASS | A |
| Harness-private read denied | unmounted private path | A04 | PASS | A |
| Harness-private write denied | unmounted private path | A05 | PASS | A |
| sealed root hidden from Actor | separate Actor mount view | A06 | PASS | A |
| symlink escape denied | chroot path resolution | A07 | PASS | A |
| loopback denied | fresh net namespace | A08 | PASS | A |
| external network denied | fresh net namespace | A09 | PASS | A |
| arbitrary parent env secret absent | sanitized env | A10 | PASS | A |
| verifier candidate write denied | ro workspace + isolated scratch | A11 + integration | PASS | A |
| oracle sealed mutation denied | ro sealed mount + seal | A12 | PASS | A |
| rootfs chmod escape denied | mount-level ro root | D13 | PASS | A |
| nested remount escape denied | dropped caps / namespace ownership | D14 | PASS on host | A |
| Unix socket host channel denied | workspace special-file preflight | D15 | PASS | A |
| external hard-link escape denied | inode/link-count preflight | D16 | PASS | A |
| profile actually uses separate oracle backend | SoftwareProfile integration | integration test | PASS | A |
| full regression | pytest | 47 passed | PASS | A |
| syntax/import compile | compileall | final validation | PASS | A |

## Final Stage 02 status

```text
PASS / EXITED
```

This matrix supersedes the rc1 matrix for current status but does not delete rc1 negative evidence. The archived rc1 report remains the historical record that Stage 02 was previously PARTIAL.
