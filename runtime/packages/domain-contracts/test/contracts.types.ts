import type { DomainManifest, DomainPolicy, DomainPolicySnapshot, DomainResolver, DomainSelection, SkillRef } from "../src"

// Compiled with the dependency-free package; never executed as runtime policy.
export function checkContractTypes(resolver: DomainResolver, manifest: DomainManifest, policy: DomainPolicy, skill: SkillRef) {
  const selection: DomainSelection = { domain: "a-new-domain", skills: [] }
  const resolved = resolver.resolve(selection)
  const wire: DomainPolicySnapshot = policy
  // @ts-expect-error Resolved policies cannot be modified through the public contract.
  resolved.policy.allowedOperations.push("mutate")
  // @ts-expect-error Nested verification policy is immutable as well.
  resolved.policy.verification.defaultStrength = "external_oracle"
  // @ts-expect-error Skills carry knowledge references, not execution permissions.
  skill.allowedOperations = ["mutate"]
  // @ts-expect-error Registration metadata cannot execute a domain or claim completion.
  manifest.run = () => "ready"
  return wire
}
