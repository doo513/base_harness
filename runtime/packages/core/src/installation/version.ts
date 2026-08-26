declare global {
  const BASE_HARNESS_VERSION: string
  const BASE_HARNESS_CHANNEL: string
}

export const InstallationVersion = typeof BASE_HARNESS_VERSION === "string" ? BASE_HARNESS_VERSION : "local"
export const InstallationChannel = typeof BASE_HARNESS_CHANNEL === "string" ? BASE_HARNESS_CHANNEL : "local"
export const InstallationLocal = InstallationChannel === "local"
