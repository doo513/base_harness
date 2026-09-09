# Provider Selection Before Initialization (2026-09-08)

## Situation
Prior local Host observations showed variable initial provider-list latency. Inspection found that enabled_providers was enforced mostly at the final active-provider filter, after several provider-specific initialization paths had already run.

## Reason
Checking only disabled_providers allowed an unlisted provider to run its model hook, authentication loader or custom initialization before being removed from the result. For example, the existing Bedrock loader can copy a stored API token into a process environment variable. This establishes avoidable work/side effects, not the complete cause of measured startup latency.

## Action
- Applied the existing isProviderAllowed policy before plugin model hooks, environment activation, API-key activation, plugin auth loaders and custom loaders.
- Applied the same check when reapplying active provider configuration.
- Preserved static catalog construction, allowed-provider behavior, disabled-over-enabled precedence and the final filter.
- Added five real Provider-service tests using only in-memory fake credentials.
- Did not add model names, reasoning-level mappings or Kernel-specific provider rules.

## Result
- New selection tests plus public metadata/reasoning tests: **21 passed**, 0 failed, 78 assertions.
- Existing Provider selection/model filter tests: **9 passed**, 0 failed, 17 assertions; 93 other tests were filtered out.
- Host typecheck: exit 0.
- Combined validation command: exit 0.

The excluded-provider test confirms no Bedrock environment-token mutation. Empty allowlists activate no providers; explicit disable overrides inclusion. Positive controls confirm explicitly allowed and default loaders still run.

## Evidence
The companion JSON records the exercised boundaries and counts. Credentials were supplied through an in-memory fixture override; the real auth file was not modified by these tests. Environment overrides were restored.
The first test command took 87.17 seconds overall despite much shorter individual cases; the existing selection command took 13.34 seconds. Setup/import/disposal costs remain unlocalized.

## Residual Risk
- This change removes known unnecessary provider-specific initialization, but does not prove a faster cold start or fix all first-catalog latency.
- Plugin registration and config hooks still run first so configuration can be established. This patch is not a plugin sandbox.
- Shared catalog, auth and environment reads still occur; it does not prohibit every access to excluded providers' metadata or credentials.
- The new tests directly observe a custom-loader side effect. They do not individually instrument each plugin hook path.
- No real OAuth flow, paid model invocation, native TUI interaction or full application regression suite was run.
- Existing unrelated pending failures and startup variance remain open. Git and net_monitor.py were not touched.
