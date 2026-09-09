import type { ProviderConfig } from "../config"
import type { SecretRegistry } from "../security/secrets"
import type { ModelProvider } from "./types"

export type ProviderFactory = (id: string, config: ProviderConfig, secrets: SecretRegistry) => ModelProvider

export class ProviderRegistry {
  private readonly factories = new Map<string, ProviderFactory>()
  private profiles: Record<string, ProviderConfig> = {}

  constructor(private readonly secrets: SecretRegistry) {}

  register(type: string, factory: ProviderFactory): void {
    if (this.factories.has(type)) throw new Error(`Provider type already registered: ${type}`)
    this.factories.set(type, factory)
  }

  configure(profiles: Record<string, ProviderConfig>): void { this.profiles = { ...profiles } }
  profileIds(): string[] { return Object.keys(this.profiles).sort() }

  create(id: string): ModelProvider {
    const profile = this.profiles[id]
    if (!profile) throw new Error(`Unknown provider profile: ${id}`)
    const factory = this.factories.get(profile.type)
    if (!factory) throw new Error(`No adapter registered for provider type: ${profile.type}`)
    return factory(id, profile, this.secrets)
  }
}
