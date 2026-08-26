import { describe, expect, test } from "bun:test"
import { InstallationChannel, InstallationVersion } from "@base-harness/core/installation/version"
import * as Installation from "@/installation"

describe("independent installation", () => {
  test("reports the bundled version without an update lookup", async () => {
    expect(await Installation.latest()).toBe(InstallationVersion)
    expect(await Installation.method()).toBe("unknown")
  })

  test("identifies the independent product", () => {
    expect(Installation.userAgent("test")).toBe(`base-harness/${InstallationChannel}/${InstallationVersion}/test`)
  })

  test("rejects automatic updates", async () => {
    await expect(Installation.upgrade("unknown", InstallationVersion)).rejects.toMatchObject({
      _tag: "UpgradeFailedError",
      message: "Automatic updates are not available in the independent base-harness distribution.",
    })
  })
})
