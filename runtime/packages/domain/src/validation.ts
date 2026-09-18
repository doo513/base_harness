import type {
  DomainErrorCode, DomainManifest, DomainOperation, DomainSelection, OverlayManifest,
  SkillRef, VerificationStrength,
} from "@base-harness/domain-contracts"

export class DomainRegistryError extends Error {
  constructor(readonly code: DomainErrorCode, readonly field?: string) {
    super(code)
    this.name = "DomainRegistryError"
  }
}

const operations = new Set<DomainOperation>(["read", "search", "question", "control", "mutate", "execute", "delegate"])
const strengths = new Set<VerificationStrength>(["structural", "execution", "behavioral", "external_oracle"])
export const identifier = (value: unknown): value is string =>
  typeof value === "string" && /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$/.test(value)
const nonempty = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value)

function object(value: unknown, keys: readonly string[], code: DomainErrorCode, field: string): Record<string, unknown> {
  if (!record(value) || Object.keys(value).some((key) => !keys.includes(key))) throw new DomainRegistryError(code, field)
  return value
}

function strings(value: unknown, code: DomainErrorCode, field: string, ids = false): string[] {
  if (!Array.isArray(value)) throw new DomainRegistryError(code, field)
  const values = [...value]
  if (!values.every(ids ? identifier : nonempty) || new Set(values).size !== values.length) {
    throw new DomainRegistryError(code, field)
  }
  return values
}

function skills(value: unknown, code: DomainErrorCode): SkillRef[] {
  if (!Array.isArray(value)) throw new DomainRegistryError(code, "skills")
  const seen = new Set<string>()
  return [...value].map((raw) => {
    const item = object(raw, ["name", "revision", "description"], code, "skills")
    if (!identifier(item.name) || !nonempty(item.revision) || !nonempty(item.description) || seen.has(item.name)) {
      throw new DomainRegistryError(code, "skills")
    }
    seen.add(item.name)
    return { name: item.name, revision: item.revision, description: item.description }
  })
}

export function parseDomainManifest(raw: unknown): DomainManifest {
  const code = "DOMAIN_MANIFEST_INVALID"
  const item = object(raw, ["schemaVersion", "id", "revision", "description", "allowedOperations", "allowedSubagentTypes",
    "planning", "verification", "measurement", "compatibleOverlays", "skills"], code, "domain")
  if (item.schemaVersion !== "domain-spec-v1" || !identifier(item.id) || !nonempty(item.revision) || !nonempty(item.description)) {
    throw new DomainRegistryError(code, "identity")
  }
  const planning = object(item.planning, ["requiresPlan", "demoFirst"], code, "planning")
  if (typeof planning.requiresPlan !== "boolean" || (planning.demoFirst !== undefined && typeof planning.demoFirst !== "boolean")) {
    throw new DomainRegistryError(code, "planning")
  }
  const verification = object(item.verification, ["defaultStrength", "criterionTemplates"], code, "verification")
  if (!strengths.has(verification.defaultStrength as VerificationStrength)) throw new DomainRegistryError(code, "verification.defaultStrength")
  const measurement = object(item.measurement, ["summarySchemaVersion", "requiredFields"], code, "measurement")
  if (measurement.summarySchemaVersion !== "evidence-summary-v1") throw new DomainRegistryError(code, "measurement.summarySchemaVersion")
  const allowedOperations = strings(item.allowedOperations, code, "allowedOperations") as DomainOperation[]
  const criterionTemplates = strings(verification.criterionTemplates, code, "verification.criterionTemplates")
  const requiredFields = strings(measurement.requiredFields, code, "measurement.requiredFields")
  if (!allowedOperations.length || allowedOperations.some((operation) => !operations.has(operation))
      || !criterionTemplates.length || !requiredFields.length) throw new DomainRegistryError(code, "policy")
  return {
    schemaVersion: "domain-spec-v1", id: item.id, revision: item.revision, description: item.description,
    allowedOperations, allowedSubagentTypes: strings(item.allowedSubagentTypes, code, "allowedSubagentTypes", true),
    planning: { requiresPlan: planning.requiresPlan, ...(planning.demoFirst === undefined ? {} : { demoFirst: planning.demoFirst }) },
    verification: { defaultStrength: verification.defaultStrength as VerificationStrength, criterionTemplates },
    measurement: { summarySchemaVersion: "evidence-summary-v1", requiredFields },
    compatibleOverlays: strings(item.compatibleOverlays, code, "compatibleOverlays", true), skills: skills(item.skills, code),
  }
}

export function parseOverlayManifest(raw: unknown): OverlayManifest {
  const code = "OVERLAY_MANIFEST_INVALID"
  const item = object(raw, ["schemaVersion", "id", "revision", "description", "defaultDomain", "compatibleDomains", "planning", "skills"], code, "overlay")
  if (item.schemaVersion !== "overlay-spec-v1" || !identifier(item.id) || !nonempty(item.revision)
      || !nonempty(item.description) || !identifier(item.defaultDomain)) throw new DomainRegistryError(code, "identity")
  const planning = object(item.planning, ["requiresPlan", "demoFirst"], code, "planning")
  if (typeof planning.requiresPlan !== "boolean" || typeof planning.demoFirst !== "boolean") throw new DomainRegistryError(code, "planning")
  const compatibleDomains = strings(item.compatibleDomains, code, "compatibleDomains", true)
  if (!compatibleDomains.includes(item.defaultDomain)) throw new DomainRegistryError(code, "defaultDomain")
  return {
    schemaVersion: "overlay-spec-v1", id: item.id, revision: item.revision, description: item.description,
    defaultDomain: item.defaultDomain, compatibleDomains,
    planning: { requiresPlan: planning.requiresPlan, demoFirst: planning.demoFirst }, skills: skills(item.skills, code),
  }
}

export function parseSelection(raw: unknown): DomainSelection {
  const code = "DOMAIN_SELECTION_INVALID"
  const item = object(raw, ["domain", "skills"], code, "selection")
  if (!identifier(item.domain) || !Array.isArray(item.skills) || item.skills.length > 64) throw new DomainRegistryError(code)
  return { domain: item.domain, skills: strings(item.skills, code, "skills", true) }
}
