# Security Boundary Hardening

## Situation

Secret redaction existed, but credential registration, run persistence, verifier transport, and status publication did not share one run-aware boundary.

## Reason

Independent sinks could retain different secret sets, and an Actor-created object could mimic the public FailureEnvelope wire shape.

## Action

A process/run `SecretRegistryHub`, Coordinator `PersistenceGateway`, verifier request redactor, non-serializable trusted-failure brand, bounded WorkGraph/event/artifact limits, and sidecar artifact quotas were added.

## Result

Persisted and published run data is redacted consistently, only host-produced failures enter verifier error handling, and unbounded evidence growth fails closed.

## Evidence

Secret variant tests, trusted-envelope tests, sidecar persistence tests, Coordinator tests, and package typechecks are the promotion evidence for this phase.
