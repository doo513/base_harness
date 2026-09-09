const record = (value: unknown): Record<string, unknown> | undefined =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined
const text = (value: unknown) => typeof value === "string" && value.length > 0 ? value : undefined

/** Presentation only: never derive retry, repair, or execution permission here. */
export function harnessResponseError(value: unknown, status?: unknown): Error {
  const error = record(value)
  const data = record(error?.data)
  const code = text(data?.code) ?? text(data?.kind) ?? text(error?.code) ?? text(error?.kind)
  const name = text(error?._tag) ?? text(error?.name)
  const message = text(data?.message) ?? text(error?.message) ?? text(value) ?? "Harness API request failed"
  const ref = text(data?.ref) ?? text(error?.ref)
  const labels = [
    code ?? (name === "Error" ? undefined : name),
    typeof status === "number" && Number.isInteger(status) ? "HTTP " + status : undefined,
    ref ? "ref " + ref : undefined,
  ].filter(Boolean)
  return new Error((labels.length ? "[" + labels.join(" | ") + "] " : "") + message)
}

export function unwrapHarnessResponse<T>(value: unknown): T {
  const outer = record(value)
  if (outer?.error !== undefined && outer.error !== null) {
    throw harnessResponseError(outer.error, record(outer.response)?.status)
  }
  return (outer?.data ?? value) as T
}
