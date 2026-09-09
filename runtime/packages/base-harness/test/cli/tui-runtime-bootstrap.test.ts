import { expect, test } from "bun:test"
import { pathToFileURL } from "node:url"
import { tmpdir } from "../fixture/fixture"
import { withTimeout } from "../../src/util/timeout"

test("TUI JSX bootstrap works outside the package without a bunfig preload", async () => {
  await using tmp = await tmpdir()
  const prepare = new URL("../../src/cli/tui/prepare-runtime.ts", import.meta.url).href
  const config = pathToFileURL(Bun.resolveSync("@base-harness/tui/config", import.meta.dir)).href
  const script = `
    const { prepareTuiRuntime } = await import(${JSON.stringify(prepare)});
    await prepareTuiRuntime();
    await prepareTuiRuntime();
    const config = await import(${JSON.stringify(config)});
    if (!config.Info || typeof config.resolve !== "function") throw new Error("TUI config did not load");
    console.log("TUI_SOURCE_BOOTSTRAP_OK");
  `
  const child = Bun.spawn([process.execPath, "--conditions=browser", "--eval", script], {
    cwd: tmp.path,
    env: { ...process.env, HOME: tmp.path, BASE_HARNESS_TEST_HOME: tmp.path },
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
  })
  const stdout = new Response(child.stdout).text()
  const stderr = new Response(child.stderr).text()
  try {
    const code = await withTimeout(child.exited, 15000, "TUI source bootstrap timed out")
    expect(await stderr).not.toContain("react/jsx")
    expect(code).toBe(0)
    expect(await stdout).toContain("TUI_SOURCE_BOOTSTRAP_OK")
  } finally {
    if (child.exitCode === null) child.kill()
    await child.exited
    await stdout
    await stderr
  }
}, 20000)
