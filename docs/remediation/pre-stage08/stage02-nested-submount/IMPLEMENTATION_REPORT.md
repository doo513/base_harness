# Stage 02 Remediation — Nested Read-Only Submount IMPLEMENTATION REPORT

Status: **red reproduction confirmed / green defense confirmed / release freeze pending**

## 1. Initial classification

The observation that `mount --rbind` followed by a top-level `remount,bind,ro` might leave descendant mounts writable was initially classified as:

> **B — Security hypothesis requiring reproduction**

It was not treated as a vulnerability from source inspection alone.

## 2. Red runtime reproduction

A dedicated probe creates this host topology inside an isolated mount namespace:

```text
source/
└── nested-mount/       # separate writable tmpfs mount
```

It then reproduces the current sandbox mounting logic against a target:

```text
mount --rbind source target
mount --make-rslave target
mount -o remount,bind,ro target
```

The probe writes through `target/nested-mount/canary`.

Result on GitHub Ubuntu 24.04 hosted runner:

```text
top_level_rbind_remount_ro_descendant_writable = true
source_canary_changed_through_descendant         = true
```

The same fixture then instantiated the actual `LinuxNamespaceSandboxBackend` with `read_only_paths=[source]`. Before remediation:

```text
preflight_blocked_nested_read_only_source = false
actual backend command returncode          = 0
actual_escape_observed                     = true
```

Therefore the finding was upgraded from hypothesis to:

> **A — Confirmed code/security defect**

Red GitHub Actions run: `31948105773`.

## 3. Root cause

`LinuxNamespaceConfigMixin._validate_ro_paths()` previously checked only:

- source existence;
- overlap with the writable workspace.

The setup script recursively bind-mounted directories, but the final top-level bind remount did not prove that descendant mounts inherited read-only state.

The implementation therefore inspected/configured the top-level mount while actual side effects could occur through a distinct descendant mount object.

This violated the remediation invariant that the object/security transition inspected must be the one actually consumed.

## 4. Defense selected

The initial remediation intentionally chooses the conservative option:

> **If a declared read-only source contains any descendant mount, fail closed before sandbox execution.**

This is preferable to claiming recursive read-only enforcement without proving the kernel/mount API behavior across supported hosts.

Implementation in `LinuxNamespaceConfigMixin`:

1. read `/proc/self/mountinfo` once during `_validate_ro_paths()`;
2. decode proc mountinfo octal escapes;
3. identify strict descendant mount points under each runtime/read-only source;
4. allow the source itself to be a mount point;
5. reject any nested mount with a descriptive `ValueError`.

Example rejection:

```text
sandbox read-only source contains nested mount(s) whose recursive read-only state is not guaranteed
```

## 5. Green runtime validation

The exact red probe remains intentionally capable of demonstrating the underlying Linux behavior. After the fix:

```text
raw top-level remount descendant writable = true
raw source canary changed                  = true
```

but the Harness defense now produces:

```text
preflight_blocked_nested_read_only_source = true
actual_backend_attempt                     = null
actual_escape_observed                     = false
defense_ok                                 = true
```

Green GitHub Actions run: `31948174266`.

Full regression at the green commit:

```text
134 passed / 5 skipped
Stage 03–07 direct probes     PASS
Stage 08 single-buffer probe  PASS 6/6
Stage 02 nested-submount      PASS
```

## 6. New tests

`tests/test_stage2_nested_submount.py` covers:

- nested mount under read-only source -> fail closed;
- source itself being a mount point -> not falsely rejected;
- octal mountinfo path decoding.

`scripts/stage2_nested_submount_probe.py` remains the security-level runtime attack fixture.

## 7. Why fail-closed instead of recursive remount now

Potential recursive mechanisms such as `mount_setattr(...AT_RECURSIVE..., MOUNT_ATTR_RDONLY)` can be investigated later, but introducing them immediately would enlarge the compatibility/kernel-support surface.

The current rule is simpler and evidence-aligned:

```text
no descendant mount -> existing read-only bind behavior
any descendant mount -> refuse execution
```

This restores safety without claiming portability that has not been tested.

## 8. Remaining limitations

- The topology is sampled before sandbox setup; highly privileged host-side concurrent topology mutation is outside the Actor threat model and would require a stronger mount-FD/namespace construction protocol.
- This does not yet solve the separate ToolSpec attestation/execution mismatch.
- GitHub hosted-runner evidence is a clean ephemeral environment, but it is not an independent third-party production host certification.
