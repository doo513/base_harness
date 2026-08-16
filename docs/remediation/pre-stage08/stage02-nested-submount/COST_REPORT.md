# Stage 02 Remediation — Nested Submount COST REPORT

## Added production cost

The defense adds one `/proc/self/mountinfo` snapshot per sandbox read-only-path preflight.

It does **not** read mountinfo once per read-only path. One parsed mount-point tuple is reused while validating all configured runtime/read-only sources in that preflight.

## Measured GitHub runner result

Probe: `scripts/remediation_mount_topology_cost_probe.py`  
GitHub Actions run: `31948301642`  
Runner: Ubuntu 24.04.4 / Python 3.11.15.

```text
rounds                           50
mountinfo bytes/read             2,457
mount points                     24
before mountinfo reads/preflight 0
after mountinfo reads/preflight  1
median parse+resolve wall time    0.0006729035 s
max observed wall time           0.0010727360 s
```

Wall time is an environment-specific proxy, not a security property.

## CPU / I/O

Before:

```text
mount topology parsing: 0
```

After:

```text
one small procfs read
+ one parse of mountinfo lines
+ descendant relation check against configured RO sources
```

For the measured runner the input was 2.4 KiB / 24 mount points. Complexity is approximately:

```text
O(mount_points + read_only_sources * mount_points)
```

The implementation deliberately avoids recursively walking `/usr` or other large source trees.

## Tool execution / wall time

The check occurs before sandbox execution. For safe topology it adds sub-millisecond median overhead on the measured host. For unsafe topology it saves the much larger cost/risk of launching a sandbox that cannot meet the declared read-only guarantee.

## Tokens / model context

No model-visible context is added. Prompt token cost is unchanged.

## Checkpoint / event / storage growth

No HarnessState, checkpoint, receipt, event-log, or artifact schema is changed by the topology check. Runtime storage growth is unchanged.

## Security-to-cost judgment

The added cost is small relative to namespace/chroot/tool process startup and directly closes a reproduced host-write escape from a declared read-only mount. The integrity benefit materially outweighs the measured preflight overhead.

A future recursive `mount_setattr` implementation may trade this fail-closed compatibility restriction for a different kernel/syscall cost, but it must first receive equivalent attack evidence.
