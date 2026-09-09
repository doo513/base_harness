/**
 * Transport compatibility for the pinned Bun runtime.
 *
 * Windows validation reproduced a fetch that never reached an idle local peer
 * when a pooled connection was reused. Fresh connections preserved both workers
 * and completed the same plan. Keep this at the transport boundary, not in model
 * selection, scheduling or verification policy.
 */
export function providerFetchOptions(
  init: BunFetchRequestInit,
  platform: NodeJS.Platform = process.platform,
): BunFetchRequestInit & { timeout: false } {
  return {
    ...init,
    ...(platform === "win32" ? { keepalive: false } : {}),
    // Retain the existing explicit header/chunk/overall AbortSignal deadlines;
    // Bun's independent idle timeout must not interrupt a valid long SSE stream.
    timeout: false,
  }
}
