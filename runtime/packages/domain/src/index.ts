import developSpec from "../resources/develop/spec.json" with { type: "json" }
import generalSpec from "../resources/general/spec.json" with { type: "json" }
import hackathonSpec from "../resources/hackathon/spec.json" with { type: "json" }
import type {
  DomainManifest, DomainPolicy, DomainSelection, DomainSelectionControl, OverlayManifest, ReadonlyValue,
} from "@base-harness/domain-contracts"
import { DomainRegistry } from "./registry"
import { builtinDomainSkillRefs } from "./skills"
export * from "./measurement"
export * from "./execution"
export * from "./autonomous-domain"
export * from "./skills"
export { DomainRegistry, DomainRegistryError } from "./registry"
export type * from "@base-harness/domain-contracts"

/** Existing resource and catalog shapes remain compatible in this stage. */
export type DomainSpec = Omit<DomainManifest, "compatibleOverlays" | "skills"> & { compatibleSkills: string[] }
export interface SkillSpec {
  schemaVersion: "skill-spec-v1"
  id: string
  revision: string
  description: string
  defaultDomain: string
  requiresPlan: boolean
  demoFirst: boolean
}
const domainSpecs: DomainSpec[] = [developSpec as DomainSpec, generalSpec as DomainSpec]
const overlaySpecs: OverlayManifest[] = [hackathonSpec as OverlayManifest]

/** Only this composition boundary knows which built-ins ship with the product. */
export const builtinDomainResolver = new DomainRegistry({
  defaultSelection: { domain: "develop", skills: [] },
  domains: domainSpecs.map(({ compatibleSkills, ...spec }) => ({
    ...spec, compatibleOverlays: compatibleSkills, skills: (builtinDomainSkillRefs[spec.id] ?? []).map((ref) => ({ ...ref })),
  })),
  overlays: overlaySpecs,
})

export function getDomainSpec(id: string): DomainSpec {
  const { compatibleOverlays, skills: _skills, ...spec } = structuredClone(builtinDomainResolver.getDomain(id)) as DomainManifest
  return { ...spec, compatibleSkills: compatibleOverlays }
}
export function getSkillSpec(id: string): SkillSpec {
  const spec = builtinDomainResolver.getOverlay(id)
  return { schemaVersion: "skill-spec-v1", id: spec.id, revision: spec.revision,
    description: spec.description, defaultDomain: spec.defaultDomain, ...spec.planning }
}
export function getOverlaySpec(id: string): OverlayManifest {
  return structuredClone(builtinDomainResolver.getOverlay(id)) as OverlayManifest
}
export const listDomainSpecs = (): DomainSpec[] => builtinDomainResolver.listDomains().map((spec) => getDomainSpec(spec.id))
export const listSkillSpecs = (): SkillSpec[] => builtinDomainResolver.listOverlays().map((spec) => getSkillSpec(spec.id))
export const listOverlaySpecs = (): OverlayManifest[] => builtinDomainResolver.listOverlays().map((spec) => getOverlaySpec(spec.id))

/** Detached compatibility view. New consumers can retain resolve().policy as a readonly snapshot. */
export const domainPolicy = (selection: ReadonlyValue<DomainSelection>): DomainPolicy =>
  structuredClone(builtinDomainResolver.resolve(selection).policy) as DomainPolicy
export const normalizeSelectionControl = (selection: ReadonlyValue<DomainSelection>, control: DomainSelectionControl): DomainSelection =>
  builtinDomainResolver.normalizeSelection(selection, control)
export const domainCatalog = Object.freeze({ domains: listDomainSpecs, skills: listSkillSpecs })
