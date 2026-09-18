import { expect, test } from "bun:test"
import yargs from "yargs"
import { joinRunMessage, RunCommand } from "../../src/cli/cmd/run"

async function parse(input: string[]) {
  let result: any
  await yargs().parserConfiguration({ "populate--": true }).exitProcess(false)
    .command({ ...RunCommand, handler: (args) => { result = args } }).parseAsync(["run", ...input])
  return result
}

for (const option of ["overlay", "disable-overlay"]) {
  test(`${option} consumes one ID per occurrence and preserves the following task`, async () => {
    const args = await parse(["--domain", "develop", `--${option}`, "hackathon", `--${option}`, "custom.overlay", "Build", "the demo"])
    expect(args[option]).toEqual(["hackathon", "custom.overlay"])
    expect(args.message).toEqual(["Build", "the demo"])
    expect(args.domain).toBe("develop")
  })
}

test("overlay options work before and after the task and with the explicit separator", async () => {
  expect((await parse(["Build demo", "--overlay", "hackathon"])).message).toEqual(["Build demo"])
  const separated = await parse(["--overlay", "hackathon", "--", "Build demo"])
  expect(separated.overlay).toEqual(["hackathon"])
  expect(separated["--"]).toEqual(["Build demo"])
})

test("natural-language argument grouping does not become literal prompt quotes", () => {
  expect(joinRunMessage(["Read source.txt and report its content"])).toBe("Read source.txt and report its content")
  expect(joinRunMessage(["Read", "source.txt"], ["and report its content"])).toBe(
    "Read source.txt and report its content",
  )
  expect(joinRunMessage(['Preserve "quoted" text'])).toBe('Preserve "quoted" text')
})
