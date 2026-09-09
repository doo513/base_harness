# Provider metadata boundary and real history verification

Date: 2026-09-08
Status: Implemented and verified within the explicit local fixture scope.

## Situation

A real HTTP response from the previous diagnostic included the deliberately fake provider API key in options. The shared toPublicInfo function serialized almost the entire live provider object. This was distinct from model authentication: the Host needs private options, but the public catalog does not.

The previous phase had implemented signed session history but had not yet demonstrated completed-run restoration in a real Host and native TUI.

## Reason

Public catalog data and live SDK configuration were insufficiently separated. Keyword masking alone would miss nonstandard credential fields, nested option bags, headers, and credential-bearing URLs.

The correct boundary is a field projection, not destruction or mutation of the private provider object. Clients select exact provider/model/variant identifiers; the Host resolves their actual authenticated runtime configuration.

## Action

- Added a pure public provider/model projection using explicit catalog fields.
- Omitted provider key and arbitrary extension fields.
- Kept provider options, model options, headers and variant option payloads empty in the public representation.
- Kept model API URL string-shaped but empty; credential-bearing endpoint details stay private.
- Preserved exact advertised model/variant names, reasoning capability lists, identity, modalities, pricing, context limits and connection metadata.
- Retained all original private runtime options and headers in Provider.Service.
- Reused the existing shared toPublicInfo boundary, covering both /provider and /config/providers without adding frontend policy.
- Added focused projection tests and a bounded real-Host metadata/authentication diagnostic.

The general /config API was deliberately not changed. Changing an editable configuration response requires a separate read/write contract review to avoid overwriting credentials with redacted placeholders.

## Result

### Selected regression gates

- Public projection tests: 6 pass, 0 fail, 37 assertions.
- Host typecheck: exit 0.
- TUI typecheck: exit 0.
- Real provider-boundary diagnostic: exit 0.

Tests cover nonstandard/nested credentials, endpoint userinfo/query/path data, exact vendor-specific effort names, original runtime configuration retention, deep-copy independence, serialization hooks and optional metadata fields.

This is not the complete regression suite.

### Actual HTTP and authenticated runtime

Both /provider and /config/providers omitted the fixture credential and private configuration payloads. The advertised high and max choices remained present with their original names.

A real headless client then selected fixture/fixture-reasoner with high. All five recorded provider requests were authenticated and carried high. The local MCP recorded its echo call. The expected result file was written and the real Python verifier produced an adaptive Ready artifact.

Session: ses_f818241d8ffe7zjSaFfvFuEE1Y
Run: run-dc847191-d067-4dc3-a6ff-762df2cd2bbe

The artifact independently inspected in this phase records a verified file-content Claim and required Criterion for the same run. It is separate from this diagnostic report; this report itself has no Evidence or Ready authority.

One measured source Host readiness sample was approximately 15.6 seconds, the first catalog request approximately 2.2 seconds, and the headless task approximately 19.2 seconds. These single samples are observations, not a performance benchmark.

### Actual Host restart and native TUI

After the execution Host had terminated, a fresh Host was started against the same state and session.

Cold HTTP status showed:
- current phase inactive
- current run ID empty
- current readyEligible false
- previous run under history with phase ready, readOnly true and revalidated false
- one past Evidence reference and five past candidate references

A native Windows PTY TUI attached to that session. Its footer showed history_ready. The /harness overlay rendered HISTORY READY, the not-reverified warning, the previous goal, Evidence/candidate counts and past adaptive assurance. The selected fixture reasoner and high label were also visible.

The TUI exited with code 0 and restored its alternate screen. A subsequent Host status query still had no current run or Ready authority. The read-only history had not become a new execution.

## Evidence

- .tools/validation/restoration-phase41-provider-public-boundary-gates.log
- .tools/validation/restoration-phase41-provider-public-boundary.result.json
- .tools/validation/restoration-phase41-provider-public-boundary-host.stdout.log
- .tools/validation/restoration-phase41-provider-public-boundary-host.stderr.log
- .tools/validation/restoration-phase41-provider-public-boundary-client.stdout.log
- .tools/validation/restoration-phase41-provider-public-boundary-client.stderr.log
- docs/evidence/PROVIDER_METADATA_BOUNDARY_AND_HISTORY_VERIFICATION_2026-09-08.json

The evidence JSON includes selected native PTY frames, actual before/after Host status, fixture request records and the separately identified verifier artifact.

## Residual Risk

- This is one author-designed deterministic local development task, not independent user validation or general model reliability evidence.
- Complex WorkGraph/repair paths, real OAuth and paid providers, multi-OS sandboxing, packaging and the full suite were not validated here.
- The earlier phase40 planned diagnostic remains failed and unchanged. This new direct-task fixture supplements it, rather than erasing that failure.
- The prior Build-tools versus Build-Tools test expectation remains unchanged.
- Public names and IDs can still contain arbitrary user-authored text; this projection is not universal secret detection.
- General /config access and remote authorization remain separate audit surfaces.
- SDK consumers that previously reconstructed provider clients from public options or URLs cannot rely on those private fields anymore. The tested TUI/headless paths use the Host instead.
- The source startup latency remains a usability concern; this patch makes no speed claim.
- The test server was loopback-only with no password. Exposed deployments require appropriate authorization.
- HMAC session history is not OS isolation and does not defeat another process with the same user's signing-key access.
- No Git commit or push was performed. net_monitor.py was not touched.

## Next work

Audit worker tool advertisement versus the Host permission boundary and continue explicit integration coverage of planned/parallel/repair work. Resolve pending test corrections with the user before changing those known defects.
