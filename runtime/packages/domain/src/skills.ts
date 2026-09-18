import type { SkillRef } from "@base-harness/domain-contracts"

/** Knowledge metadata only; body discovery and permission checks belong to the application. */
export const builtinDomainSkillRefs: Readonly<Record<string, readonly Readonly<SkillRef>[]>> = Object.freeze({
  general: Object.freeze([Object.freeze({
    name: "domain-general", revision: "1", description: "Source-grounded, read-only research and reporting.",
  })]),
  develop: Object.freeze([Object.freeze({
    name: "domain-develop", revision: "1", description: "Contract-scoped development, Candidate changes, and verification handoff.",
  })]),
})
