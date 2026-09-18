import type {
  DomainManifest, DomainPolicy, DomainResolver, DomainSelection, DomainSelectionControl,
  OverlayManifest, ReadonlyValue, ResolvedDomain, SkillRef,
} from "@base-harness/domain-contracts"
import { DomainRegistryError, identifier, parseDomainManifest, parseOverlayManifest, parseSelection } from "./validation"
export { DomainRegistryError } from "./validation"

function freeze<T>(value: T): ReadonlyValue<T> {
  if (value !== null && typeof value === "object") {
    for (const item of Object.values(value)) freeze(item)
    Object.freeze(value)
  }
  return value as ReadonlyValue<T>
}

/** Immutable, explicitly registered metadata. Resolution never invokes I/O or domain code. */
export class DomainRegistry implements DomainResolver {
  readonly defaultSelection: ReadonlyValue<DomainSelection>
  readonly #domains = new Map<string, ReadonlyValue<DomainManifest>>()
  readonly #overlays = new Map<string, ReadonlyValue<OverlayManifest>>()
  readonly #resolved = new Map<string, ResolvedDomain>()

  constructor(input: {
    defaultSelection: ReadonlyValue<DomainSelection>
    domains: readonly ReadonlyValue<DomainManifest>[]
    overlays?: readonly ReadonlyValue<OverlayManifest>[]
  }) {
    if (!input || !Array.isArray(input.domains) || (input.overlays !== undefined && !Array.isArray(input.overlays))) {
      throw new DomainRegistryError("DOMAIN_REGISTRATION_INVALID")
    }
    for (const raw of input.domains) {
      const manifest = parseDomainManifest(raw)
      if (this.#domains.has(manifest.id)) throw new DomainRegistryError("DOMAIN_DUPLICATE", manifest.id)
      this.#domains.set(manifest.id, freeze(manifest))
    }
    for (const raw of input.overlays ?? []) {
      const overlay = parseOverlayManifest(raw)
      if (this.#overlays.has(overlay.id)) throw new DomainRegistryError("OVERLAY_DUPLICATE", overlay.id)
      this.#overlays.set(overlay.id, freeze(overlay))
    }
    for (const manifest of this.#domains.values()) {
      for (const id of manifest.compatibleOverlays) {
        if (!this.#overlays.get(id)?.compatibleDomains.includes(manifest.id)) {
          throw new DomainRegistryError("DOMAIN_REGISTRATION_INVALID", `${manifest.id}.compatibleOverlays`)
        }
      }
    }
    for (const overlay of this.#overlays.values()) {
      for (const id of overlay.compatibleDomains) {
        if (!this.#domains.get(id)?.compatibleOverlays.includes(overlay.id)) {
          throw new DomainRegistryError("DOMAIN_REGISTRATION_INVALID", `${overlay.id}.compatibleDomains`)
        }
      }
    }
    this.defaultSelection = freeze(parseSelection(input.defaultSelection))
    this.resolve(this.defaultSelection)
    Object.freeze(this)
  }

  getDomain(id: string): ReadonlyValue<DomainManifest> {
    const manifest = identifier(id) ? this.#domains.get(id) : undefined
    if (!manifest) throw new DomainRegistryError("DOMAIN_UNKNOWN", "domain")
    return manifest
  }

  getOverlay(id: string): ReadonlyValue<OverlayManifest> {
    const overlay = identifier(id) ? this.#overlays.get(id) : undefined
    if (!overlay) throw new DomainRegistryError("OVERLAY_UNKNOWN", "skill")
    return overlay
  }

  listDomains(): readonly ReadonlyValue<DomainManifest>[] { return Object.freeze([...this.#domains.values()]) }
  listOverlays(): readonly ReadonlyValue<OverlayManifest>[] { return Object.freeze([...this.#overlays.values()]) }

  resolve(input: ReadonlyValue<DomainSelection>): ResolvedDomain {
    const selection = parseSelection(input)
    // Preserve modifier order on the existing verifier wire, including its revision list.
    const key = JSON.stringify([selection.domain, selection.skills])
    const cached = this.#resolved.get(key)
    if (cached) return cached
    const manifest = this.getDomain(selection.domain)
    const overlays = selection.skills.map((id) => {
      const overlay = this.getOverlay(id)
      if (!manifest.compatibleOverlays.includes(id) || !overlay.compatibleDomains.includes(manifest.id)) {
        throw new DomainRegistryError("DOMAIN_SKILL_INCOMPATIBLE", id)
      }
      return overlay
    })
    const skillRefs = new Map<string, ReadonlyValue<SkillRef>>()
    for (const skill of [...manifest.skills, ...overlays.flatMap((overlay) => overlay.skills)]) {
      const previous = skillRefs.get(skill.name)
      if (previous && (previous.revision !== skill.revision || previous.description !== skill.description)) {
        throw new DomainRegistryError("DOMAIN_SKILL_CONFLICT", skill.name)
      }
      skillRefs.set(skill.name, skill)
    }
    const policy: DomainPolicy = {
      domainId: manifest.id, domainRevision: manifest.revision, skillRevisions: overlays.map((overlay) => overlay.revision),
      allowedOperations: [...manifest.allowedOperations], allowedSubagentTypes: [...manifest.allowedSubagentTypes],
      requiresPlan: manifest.planning.requiresPlan || overlays.some((overlay) => overlay.planning.requiresPlan),
      demoFirst: Boolean(manifest.planning.demoFirst || overlays.some((overlay) => overlay.planning.demoFirst)),
      verification: { defaultStrength: manifest.verification.defaultStrength, criterionTemplates: [...manifest.verification.criterionTemplates] },
      measurement: { summarySchemaVersion: manifest.measurement.summarySchemaVersion, requiredFields: [...manifest.measurement.requiredFields] },
    }
    const result: ResolvedDomain = freeze({ selection, policy, skills: [...skillRefs.values()] })
    // Bound memory without changing the policy held by an existing consumer.
    if (this.#resolved.size >= 256) this.#resolved.delete(this.#resolved.keys().next().value!)
    this.#resolved.set(key, result)
    return result
  }

  normalizeSelection(input: ReadonlyValue<DomainSelection>, control: DomainSelectionControl): DomainSelection {
    const current = this.resolve(input).selection
    if (!control || typeof control !== "object") throw new DomainRegistryError("DOMAIN_CONTROL_INVALID")
    if (control.type === "domain.set") {
      const next = { domain: control.domain, skills: [] }
      this.resolve(next)
      return next
    }
    if (control.type !== "skill.set" || typeof control.enabled !== "boolean") throw new DomainRegistryError("DOMAIN_CONTROL_INVALID")
    const overlay = this.getOverlay(control.skill)
    const retained = current.skills.filter((id) => id !== overlay.id)
    const next = !control.enabled ? { domain: current.domain, skills: retained } : {
      domain: overlay.compatibleDomains.includes(current.domain) ? current.domain : overlay.defaultDomain,
      skills: [...retained, overlay.id],
    }
    this.resolve(next)
    return next
  }
}
