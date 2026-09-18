import type { InterpretationProposal, ContractPreflightSignals, ContractPreflightResult } from "@base-harness/domain-contracts"
import { prepareContractPreflight } from "./prepare"
import { scanContractPreflight } from "./scan"
import { validateAndDedupeContractPreflight } from "./validate"

/** Compatibility entry point for callers that do not need stage artifacts. */
export function decideContractPreflight(
  proposal: InterpretationProposal,
  signals: ContractPreflightSignals,
): ContractPreflightResult {
  return validateAndDedupeContractPreflight(
    scanContractPreflight(prepareContractPreflight(proposal, signals)),
  ).result
}

