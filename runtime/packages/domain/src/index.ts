import developSpec from "../resources/develop/spec.json" with { type: "json" }
import generalSpec from "../resources/general/spec.json" with { type: "json" }
import hackathonSpec from "../resources/hackathon/spec.json" with { type: "json" }
export * from "./measurement"

export type DomainId = "develop" | "general"
export type SkillId = "hackathon"
export type DomainOperation =
  | "read"
  | "search"
  | "question"
  | "control"
  | "mutate"
  | "execute"
  | "delegate"

export interface DomainSpec {
  schemaVersion: "domain-spec-v1"
  id: DomainId
  revision: string
  description: string
  allowedOperations: DomainOperation[]
  allowedSubagentTypes: string[]
  planning: {
    requiresPlan: boolean
    demoFirst?: boolean
  }
  verification: {
    defaultStrength: "structural" | "execution" | "behavioral" | "external_oracle"
    criterionTemplates: string[]
  }
  measurement: {
    summarySchemaVersion: "evidence-summary-v1"
    requiredFields: string[]
  }
  compatibleSkills: SkillId[]
}

export interface SkillSpec {
  schemaVersion: "skill-spec-v1"
  id: SkillId
  revision: string
  description: string
  defaultDomain: DomainId
  requiresPlan: boolean
  demoFirst: boolean
}

export interface DomainSelection {
  domain: DomainId
  skills: SkillId[]
}

export interface DomainPolicy {
  domainId: DomainId
  domainRevision: string
  skillRevisions: string[]
  allowedOperations: DomainOperation[]
  allowedSubagentTypes: string[]
  requiresPlan: boolean
  demoFirst: boolean
  verification: DomainSpec["verification"]
  measurement: DomainSpec["measurement"]
}

const domains: Record<DomainId, DomainSpec> = {
  develop: developSpec as DomainSpec,
  general: generalSpec as DomainSpec,
}

const skills: Record<SkillId, SkillSpec> = {
  hackathon: hackathonSpec as SkillSpec,
}

export function getDomainSpec(id: DomainId): DomainSpec {
  return domains[id]
}

export function getSkillSpec(id: SkillId): SkillSpec {
  return skills[id]
}

export function listDomainSpecs(): DomainSpec[] {
  return Object.values(domains).map((spec) => ({
    ...spec,
    allowedOperations: [...spec.allowedOperations],
    allowedSubagentTypes: [...spec.allowedSubagentTypes],
    planning: { ...spec.planning },
    verification: {
      ...spec.verification,
      criterionTemplates: [...spec.verification.criterionTemplates],
    },
    measurement: {
      ...spec.measurement,
      requiredFields: [...spec.measurement.requiredFields],
    },
    compatibleSkills: [...spec.compatibleSkills],
  }))
}

export function listSkillSpecs(): SkillSpec[] {
  return Object.values(skills).map((spec) => ({ ...spec }))
}

export function domainPolicy(selection: DomainSelection): DomainPolicy {
  const domain = getDomainSpec(selection.domain)
  const selectedSkills = selection.skills.map(getSkillSpec)
  if (selectedSkills.some((skill) => !domain.compatibleSkills.includes(skill.id))) {
    throw new Error("DOMAIN_SKILL_INCOMPATIBLE")
  }
  return {
    domainId: domain.id,
    domainRevision: domain.revision,
    skillRevisions: selectedSkills.map((skill) => skill.revision),
    allowedOperations: [...domain.allowedOperations],
    allowedSubagentTypes: [...domain.allowedSubagentTypes],
    requiresPlan: domain.planning.requiresPlan || selectedSkills.some((skill) => skill.requiresPlan),
    demoFirst: Boolean(domain.planning.demoFirst || selectedSkills.some((skill) => skill.demoFirst)),
    verification: {
      defaultStrength: domain.verification.defaultStrength,
      criterionTemplates: [...domain.verification.criterionTemplates],
    },
    measurement: {
      summarySchemaVersion: domain.measurement.summarySchemaVersion,
      requiredFields: [...domain.measurement.requiredFields],
    },
  }
}

/** Applies domain/skill compatibility once for Host and TUI preview state. */
export function normalizeSelectionControl(
  selection: DomainSelection,
  control:
    | { type: "domain.set"; domain: DomainId }
    | { type: "skill.set"; skill: SkillId; enabled: boolean },
): DomainSelection {
  if (control.type === "domain.set") {
    return { domain: control.domain, skills: [] }
  }

  const skill = getSkillSpec(control.skill)
  if (!control.enabled) {
    return { domain: selection.domain, skills: selection.skills.filter((item) => item !== skill.id) }
  }

  const domain = getDomainSpec(selection.domain).compatibleSkills.includes(skill.id)
    ? selection.domain
    : skill.defaultDomain
  return { domain, skills: [...new Set([...selection.skills.filter((item) => item !== skill.id), skill.id])] }
}

export const domainCatalog = Object.freeze({
  domains: listDomainSpecs,
  skills: listSkillSpecs,
})
