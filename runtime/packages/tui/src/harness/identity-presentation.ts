import { Locale } from "../util/locale"

const productName = "Base Harness"

export function harnessTerminalTitle(detail?: string): string {
  return detail ? `${productName} | ${detail}` : productName
}

/** Keep legacy execution roles internal; the Host domain remains in the harness status UI. */
export function harnessActorLabel(role: string): string {
  if (role === "build" || role === "plan") return productName
  return Locale.titlecase(role)
}
