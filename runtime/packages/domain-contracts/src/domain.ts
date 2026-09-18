/** Names are owned by the registry, never enumerated by the Kernel. */
export type DomainId = string
export type SkillId = string
export type OverlayId = string
export type DomainOperation = "read" | "search" | "question" | "control" | "mutate" | "execute" | "delegate"
export type VerificationStrength = "structural" | "execution" | "behavioral" | "external_oracle"

export type ReadonlyValue<T> = T extends readonly (infer Item)[]
  ? readonly ReadonlyValue<Item>[]
  : T extends object ? { readonly [Key in keyof T]: ReadonlyValue<T[Key]> } : T

export interface DomainSelection {
  domain: DomainId
  /** Existing wire name for selected policy modifiers. Skill prose grants no policy. */
  skills: OverlayId[]
}

export type DomainSelectionControl =
  | { type: "domain.set"; domain: DomainId }
  | { type: "skill.set"; skill: OverlayId; enabled: boolean }

/** Knowledge reference only. The application loads bodies through its Skill and permission services. */
export interface SkillRef {
  name: SkillId
  revision: string
  description: string
}

/** Existing verifier wire shape; no authority or execution callbacks are included. */
export interface DomainPolicySnapshot {
  domainId: DomainId
  domainRevision: string
  skillRevisions: string[]
  allowedOperations: string[]
  allowedSubagentTypes: string[]
  requiresPlan: boolean
  demoFirst: boolean
  verification: {
    defaultStrength: VerificationStrength
    criterionTemplates: string[]
  }
  measurement: {
    summarySchemaVersion: string
    requiredFields: string[]
  }
}

export interface DomainPolicy extends DomainPolicySnapshot {
  allowedOperations: DomainOperation[]
  measurement: { summarySchemaVersion: "evidence-summary-v1"; requiredFields: string[] }
}

export interface DomainManifest {
  schemaVersion: "domain-spec-v1"
  id: DomainId
  revision: string
  description: string
  allowedOperations: DomainOperation[]
  allowedSubagentTypes: string[]
  planning: { requiresPlan: boolean; demoFirst?: boolean }
  verification: DomainPolicy["verification"]
  measurement: DomainPolicy["measurement"]
  compatibleOverlays: OverlayId[]
  skills: SkillRef[]
}

/** Typed policy metadata, separate from Skill prose and executable overlay strategies. */
export interface OverlayManifest {
  schemaVersion: "overlay-spec-v1"
  id: OverlayId
  revision: string
  description: string
  defaultDomain: DomainId
  compatibleDomains: DomainId[]
  planning: { requiresPlan: boolean; demoFirst: boolean }
  skills: SkillRef[]
}

export interface ResolvedDomain {
  readonly selection: ReadonlyValue<DomainSelection>
  readonly policy: ReadonlyValue<DomainPolicy>
  readonly skills: readonly ReadonlyValue<SkillRef>[]
}

export interface DomainResolver {
  readonly defaultSelection: ReadonlyValue<DomainSelection>
  resolve(selection: ReadonlyValue<DomainSelection>): ResolvedDomain
  normalizeSelection(selection: ReadonlyValue<DomainSelection>, control: DomainSelectionControl): DomainSelection
}

export type DomainErrorCode =
  | "DOMAIN_REGISTRATION_INVALID" | "DOMAIN_MANIFEST_INVALID" | "OVERLAY_MANIFEST_INVALID"
  | "DOMAIN_DUPLICATE" | "OVERLAY_DUPLICATE" | "DOMAIN_UNKNOWN" | "OVERLAY_UNKNOWN"
  | "DOMAIN_SELECTION_INVALID" | "DOMAIN_CONTROL_INVALID" | "DOMAIN_SKILL_INCOMPATIBLE"
  | "DOMAIN_SKILL_CONFLICT"
