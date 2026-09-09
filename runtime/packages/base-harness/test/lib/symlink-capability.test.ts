import { expect, test } from "bun:test"
import { requireSymlinkCapabilities, unavailableSymlinkReason } from "./symlink-capability"

test("only expected Windows privilege failures become unsupported capabilities", () => {
  for (const code of ["EPERM", "EACCES"]) {
    expect(unavailableSymlinkReason({ code }, "win32")).toContain(code)
    expect(unavailableSymlinkReason({ code }, "linux")).toBeUndefined()
  }
  for (const code of ["ENOENT", "EIO", "ENOSPC", "EINVAL"]) {
    expect(unavailableSymlinkReason({ code }, "win32")).toBeUndefined()
  }
  expect(unavailableSymlinkReason(null, "win32")).toBeUndefined()
  expect(unavailableSymlinkReason("EPERM", "win32")).toBeUndefined()
})

test("required symlink gate rejects every unsupported combination", () => {
  for (const file of [true, false]) for (const directory of [true, false]) {
    const capabilities = { file: { supported: file }, directory: { supported: directory } }
    expect(() => requireSymlinkCapabilities(capabilities, false)).not.toThrow()
    if (file && directory) expect(() => requireSymlinkCapabilities(capabilities, true)).not.toThrow()
    else expect(() => requireSymlinkCapabilities(capabilities, true)).toThrow("SYMLINK_CAPABILITY_REQUIRED")
  }
})
