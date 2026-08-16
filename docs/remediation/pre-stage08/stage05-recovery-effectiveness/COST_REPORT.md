# Stage05 Recovery Effectiveness — Cost Report

## Controlled benchmark cost

Across the three recovered pairs, Recovery added relative to the fail-closed baseline:

- total persisted steps: `+7`;
- total task tool calls: `+4`;
- steps per recovered success: `+2.3333333333333335`;
- tool calls per recovered success: `+1.3333333333333333`.

The increase is expected: the baseline halts immediately after the first nonterminal failure, while the Recovery arm applies a control transition, returns a directive to the Actor and permits additional evidence-producing action.

## Safety cost boundary

The terminal-security pair added no unsafe continuation:

- Recovery completed: false;
- baseline completed: false;
- unsafe handler executions: 0 / 0;
- unsafe retries: 0.

## Interpretation

This report does not claim the additional actions are economically optimal. It only records the deterministic incremental action cost corresponding to three additional accepted completions in the frozen benchmark. Token/model cost is not measured because the benchmark controller is deterministic and does not invoke a model.
