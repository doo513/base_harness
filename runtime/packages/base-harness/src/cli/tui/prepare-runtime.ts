/** Source launches must not depend on the user's cwd containing our bunfig.toml. */
export async function prepareTuiRuntime() {
  const { ensureSolidTransformPlugin } = await import("@opentui/solid/bun-plugin")
  ensureSolidTransformPlugin()
}
