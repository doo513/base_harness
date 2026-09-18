import { expect, test } from "bun:test"
import {
  builtinDomainResolver, domainCatalog, domainPolicy, DomainRegistry, DomainRegistryError,
  getDomainSpec, getOverlaySpec, getSkillSpec, listOverlaySpecs, normalizeSelectionControl,
} from "../src"
import type { DomainManifest, DomainSelection, OverlayManifest, SkillRef } from "@base-harness/domain-contracts"
import develop from "../resources/develop/spec.json"
import general from "../resources/general/spec.json"
import hackathon from "../resources/hackathon/spec.json"

const selection = (domain = "research", skills: string[] = []): DomainSelection => ({ domain, skills })
const knowledge: SkillRef = { name: "research-notes", revision: "1", description: "Compare the provided sources." }
function manifest(id = "research"): DomainManifest {
  return {
    schemaVersion: "domain-spec-v1", id, revision: "r1", description: "Fixture research policy",
    allowedOperations: ["read", "search", "control"], allowedSubagentTypes: ["explore"],
    planning: { requiresPlan: false },
    verification: { defaultStrength: "structural", criterionTemplates: ["observation"] },
    measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields: ["observed"] },
    compatibleOverlays: [], skills: [knowledge],
  }
}
function registry(domain = manifest()) { return new DomainRegistry({ defaultSelection: selection(domain.id), domains: [domain] }) }
function overlay(id = "brief"): OverlayManifest {
  return {
    schemaVersion: "overlay-spec-v1", id, revision: id + "-1", description: "Fixture planning modifier",
    defaultDomain: "research", compatibleDomains: ["research"],
    planning: { requiresPlan: true, demoFirst: false }, skills: [knowledge],
  }
}
function withOverlays(overlays = [overlay()]) {
  const domain = manifest()
  domain.compatibleOverlays = [...new Set(overlays.map((item) => item.id))]
  return new DomainRegistry({ defaultSelection: selection(), domains: [domain], overlays })
}
function errorCode(action: () => unknown) {
  try { action() } catch (error) {
    expect(error).toBeInstanceOf(DomainRegistryError)
    return (error as DomainRegistryError).code
  }
  throw new Error("Expected a domain error")
}

test("legacy catalogs retain their resource shapes and return detached values", () => {
  expect<unknown>(getDomainSpec("develop")).toEqual(develop)
  expect<unknown>(getDomainSpec("general")).toEqual(general)
  expect<unknown>(getOverlaySpec("hackathon")).toEqual(hackathon)
  expect<unknown>(listOverlaySpecs()).toEqual([hackathon])
  const legacyHackathon = {
    schemaVersion: "skill-spec-v1", id: hackathon.id, revision: hackathon.revision,
    description: hackathon.description, defaultDomain: hackathon.defaultDomain,
    requiresPlan: hackathon.planning.requiresPlan, demoFirst: hackathon.planning.demoFirst,
  }
  expect<unknown>(getSkillSpec("hackathon")).toEqual(legacyHackathon)
  expect<unknown>(domainCatalog.domains()).toEqual([develop, general])
  expect<unknown>(domainCatalog.skills()).toEqual([legacyHackathon])
  getDomainSpec("develop").allowedOperations.length = 0
  domainCatalog.domains()[0]!.verification.criterionTemplates.length = 0
  const mutable = domainPolicy(selection("develop"))
  mutable.allowedOperations.length = 0
  mutable.measurement.requiredFields.length = 0
  expect<unknown>(getDomainSpec("develop")).toEqual(develop)
  expect(domainPolicy(selection("develop")).allowedOperations).toContain("mutate")
  expect(domainPolicy(selection("develop")).measurement.requiredFields).toEqual(develop.measurement.requiredFields)
})

test("built-in policy behavior and legacy selection controls remain compatible", () => {
  expect<unknown>(domainPolicy(selection("general"))).toEqual({
    domainId: "general", domainRevision: "general-1", skillRevisions: [],
    allowedOperations: ["read", "search", "question", "control", "delegate"], allowedSubagentTypes: ["explore"],
    requiresPlan: false, demoFirst: false, verification: general.verification, measurement: general.measurement,
  })
  const base = domainPolicy(selection("develop"))
  const selected = normalizeSelectionControl(selection("general"), { type: "skill.set", skill: "hackathon", enabled: true })
  expect(selected).toEqual(selection("develop", ["hackathon"]))
  expect(domainPolicy(selected)).toEqual({ ...base, skillRevisions: ["hackathon-1"], requiresPlan: true, demoFirst: true })
  expect(normalizeSelectionControl(selected, { type: "skill.set", skill: "hackathon", enabled: true })).toEqual(selected)
  expect(normalizeSelectionControl(selected, { type: "skill.set", skill: "hackathon", enabled: false })).toEqual(selection("develop"))
  expect(normalizeSelectionControl(selected, { type: "domain.set", domain: "general" })).toEqual(selection("general"))
})

test("built-in selections carry knowledge references independently of operation policy", () => {
  expect(builtinDomainResolver.resolve(selection("general")).skills.map((ref) => ref.name)).toEqual(["domain-general"])
  expect(builtinDomainResolver.resolve(selection("develop")).skills.map((ref) => ref.name)).toEqual(["domain-develop"])
  const demo = builtinDomainResolver.resolve(selection("develop", ["hackathon"]))
  expect(demo.skills.map((ref) => [ref.name, ref.revision])).toEqual([["domain-develop", "1"], ["hackathon-demo", "1"]])
  expect(demo.policy.allowedOperations).toEqual(domainPolicy(selection("develop")).allowedOperations)
})

test("registry, registrations, nested snapshots and selection inputs cannot mutate a resolved policy", () => {
  const source = manifest(), input = selection(), instance = registry(source)
  const resolved = instance.resolve(input)
  source.allowedOperations.length = 0
  source.skills[0] = { ...knowledge, revision: "changed" }
  input.skills.push("other")
  expect(resolved.selection).toEqual(selection())
  expect(resolved.policy.allowedOperations).toContain("read")
  expect(resolved.skills[0]!.revision).toBe("1")
  for (const mutate of [
    () => { (resolved.policy.allowedOperations as any).push("mutate") },
    () => { (resolved.policy.verification as any).defaultStrength = "external_oracle" },
    () => { (instance.getDomain("research").skills[0] as any).revision = "changed" },
    () => { (instance.defaultSelection as any).domain = "unknown" },
    () => { (instance as any).defaultSelection = selection("unknown") },
    () => { (instance.listDomains() as any).push(manifest("new")) },
  ]) expect(mutate).toThrow()
  expect(instance.resolve(selection())).toBe(resolved)
})

test("independent registries and cached policies keep their own revision and permissions", () => {
  const first = registry(), changed = manifest()
  changed.revision = "r2"
  changed.allowedOperations.push("mutate")
  const second = registry(changed)
  const retained = first.resolve(selection())
  for (let index = 0; index < 20; index++) expect(first.resolve(selection())).toBe(retained)
  expect(second.resolve(selection()).policy).toMatchObject({ domainRevision: "r2" })
  expect(second.resolve(selection()).policy.allowedOperations).toContain("mutate")
  expect(retained.policy.allowedOperations).not.toContain("mutate")
})

test("bounded cache eviction does not change policy values or an existing consumer snapshot", () => {
  const domains = Array.from({ length: 260 }, (_, index) => manifest("domain-" + index))
  const instance = new DomainRegistry({ defaultSelection: selection(domains[0]!.id), domains })
  const first = instance.resolve(selection("domain-0"))
  for (const domain of domains) instance.resolve(selection(domain.id))
  const resolvedAgain = instance.resolve(selection("domain-0"))
  expect(resolvedAgain).not.toBe(first)
  expect(resolvedAgain).toEqual(first)
  expect(Object.isFrozen(first.policy)).toBe(true)
})

for (const raw of [null, [], {}, { domain: "research" }, selection(""), selection("research", ["brief", "brief"]),
  { ...selection(), skills: [7] }, { ...selection(), skills: new Array(1) }, { ...selection(), ready: true }]) {
  test(`invalid selection fails with a typed diagnostic: ${JSON.stringify(raw)}`, () => {
    expect(errorCode(() => registry().resolve(raw as any))).toBe("DOMAIN_SELECTION_INVALID")
  })
}

test("unknown names and incompatible choices never fall back or damage valid resolutions", () => {
  const instance = withOverlays(), valid = instance.resolve(selection())
  for (const domain of ["unknown", "constructor", "toString", "ctf"]) {
    expect(errorCode(() => instance.resolve(selection(domain)))).toBe("DOMAIN_UNKNOWN")
  }
  expect(errorCode(() => instance.resolve(selection("research", ["missing"])))).toBe("OVERLAY_UNKNOWN")
  expect(errorCode(() => builtinDomainResolver.resolve(selection("general", ["hackathon"])))).toBe("DOMAIN_SKILL_INCOMPATIBLE")
  expect(instance.resolve(selection())).toBe(valid)
  expect(() => getDomainSpec("constructor")).toThrow("DOMAIN_UNKNOWN")
  expect(() => getSkillSpec("constructor")).toThrow("OVERLAY_UNKNOWN")
})

for (const control of [null, { type: "execute" }, { type: "skill.set", skill: "brief", enabled: "false" }]) {
  test(`invalid selection control is rejected: ${JSON.stringify(control)}`, () => {
    expect(errorCode(() => withOverlays().normalizeSelection(selection(), control as any))).toBe("DOMAIN_CONTROL_INVALID")
  })
}

test("cross-domain modifier fallback preserves earlier selections and rejects incompatible combinations", () => {
  const a = manifest("a"), b = manifest("b")
  a.compatibleOverlays = ["only-a"]; b.compatibleOverlays = ["only-b"]
  const overlays = ["a", "b"].map((id) => ({ ...overlay("only-" + id), defaultDomain: id, compatibleDomains: [id] }))
  const instance = new DomainRegistry({ defaultSelection: selection("a"), domains: [a, b], overlays })
  expect(instance.normalizeSelection(selection("a"), { type: "skill.set", skill: "only-b", enabled: true })).toEqual(selection("b", ["only-b"]))
  const prior = selection("a", ["only-a"])
  expect(errorCode(() => instance.normalizeSelection(prior, { type: "skill.set", skill: "only-b", enabled: true }))).toBe("DOMAIN_SKILL_INCOMPATIBLE")
  expect(prior).toEqual(selection("a", ["only-a"]))
})

test("modifiers keep ordered revisions, deduplicate knowledge references, and cannot expand authority", () => {
  const instance = withOverlays([overlay("first"), { ...overlay("second"), planning: { requiresPlan: false, demoFirst: true } }])
  const base = instance.resolve(selection()).policy
  const resolved = instance.resolve(selection("research", ["second", "first"]))
  expect(resolved.policy).toEqual({ ...base, skillRevisions: ["second-1", "first-1"], requiresPlan: true, demoFirst: true })
  expect(resolved.skills).toEqual([knowledge])
  const escalated = { ...overlay(), allowedOperations: ["mutate"] }
  expect(errorCode(() => withOverlays([escalated as any]))).toBe("OVERLAY_MANIFEST_INVALID")
})

test("conflicting knowledge references are diagnosed without poisoning valid selections", () => {
  const conflicting = { ...overlay(), skills: [{ ...knowledge, revision: "2" }] }
  const instance = withOverlays([conflicting])
  expect(errorCode(() => instance.resolve(selection("research", ["brief"])))).toBe("DOMAIN_SKILL_CONFLICT")
  expect(instance.resolve(selection()).skills).toEqual([knowledge])
})

const invalidManifest: Array<[string, (input: DomainManifest) => unknown]> = [
  ["schema", (input) => ({ ...input, schemaVersion: "unknown" })],
  ["identity", (input) => ({ ...input, id: "" })],
  ["revision", (input) => ({ ...input, revision: " " })],
  ["operation", (input) => ({ ...input, allowedOperations: ["unknown-operation"] })],
  ["sparse operation", (input) => ({ ...input, allowedOperations: new Array(1) })],
  ["sparse knowledge", (input) => ({ ...input, skills: new Array(1) })],
  ["duplicate operation", (input) => ({ ...input, allowedOperations: ["read", "read"] })],
  ["planning boolean", (input) => ({ ...input, planning: { requiresPlan: "false" } })],
  ["verification", (input) => ({ ...input, verification: { ...input.verification, defaultStrength: "guess" } })],
  ["empty verifier templates", (input) => ({ ...input, verification: { ...input.verification, criterionTemplates: [] } })],
  ["measurement", (input) => ({ ...input, measurement: { ...input.measurement, requiredFields: [] } })],
  ["knowledge", (input) => ({ ...input, skills: [{ name: "notes", revision: "" }] })],
  ["execution callback", (input) => ({ ...input, run: () => "ready" })],
]
for (const [name, change] of invalidManifest) test(`invalid domain metadata is rejected: ${name}`, () => {
  expect(errorCode(() => registry(change(manifest()) as any))).toBe("DOMAIN_MANIFEST_INVALID")
})

test("duplicate registration, broken compatibility references and unknown defaults fail at construction", () => {
  expect(errorCode(() => new DomainRegistry({ defaultSelection: selection(), domains: [manifest(), manifest()] }))).toBe("DOMAIN_DUPLICATE")
  expect(errorCode(() => withOverlays([overlay(), overlay()]))).toBe("OVERLAY_DUPLICATE")
  expect(errorCode(() => new DomainRegistry({ defaultSelection: selection("absent"), domains: [manifest()] }))).toBe("DOMAIN_UNKNOWN")
  expect(errorCode(() => registry({ ...manifest(), compatibleOverlays: ["missing"] }))).toBe("DOMAIN_REGISTRATION_INVALID")
  const oneSided = { ...overlay(), compatibleDomains: ["research", "missing"] }
  expect(errorCode(() => withOverlays([oneSided]))).toBe("DOMAIN_REGISTRATION_INVALID")
  expect(errorCode(() => withOverlays([{ ...overlay(), defaultDomain: "missing" }]))).toBe("OVERLAY_MANIFEST_INVALID")
  expect(errorCode(() => withOverlays([{ ...overlay(), planning: { requiresPlan: "false" as any, demoFirst: false } }]))).toBe("OVERLAY_MANIFEST_INVALID")
})
