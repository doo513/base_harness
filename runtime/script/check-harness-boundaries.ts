import { promises as fs } from "node:fs"
import path from "node:path"
import ts from "typescript"

const runtimeRoot = path.resolve(import.meta.dir, "..")
const packageRoot = path.join(runtimeRoot, "packages")
const errors: string[] = []

async function sourceFiles(directory: string): Promise<string[]> {
  const entries = await fs.readdir(directory, { withFileTypes: true })
  const output: string[] = []
  for (const entry of entries) {
    if (entry.name === "node_modules" || entry.name === "dist") continue
    const target = path.join(directory, entry.name)
    if (entry.isDirectory()) output.push(...(await sourceFiles(target)))
    else if (/\.tsx?$/.test(entry.name)) output.push(target)
  }
  return output
}

const roots = {
  host: path.join(packageRoot, "base-harness", "src"),
  tui: path.join(packageRoot, "tui", "src"),
  core: path.join(packageRoot, "core", "src"),
  verification: path.join(packageRoot, "verification", "src"),
  coordinator: path.join(packageRoot, "coordinator", "src"),
  kernel: path.join(packageRoot, "kernel", "src"),
  kernelHost: path.join(packageRoot, "kernel-host", "src"),
  workspace: path.join(packageRoot, "workspace", "src"),
  security: path.join(packageRoot, "security", "src"),
}
const facade = path.join(roots.host, "harness", "coordinator-service.ts")

for (const [area, root] of Object.entries(roots)) {
  for (const file of await sourceFiles(root)) {
    const source = ts.createSourceFile(file, await fs.readFile(file, "utf8"), ts.ScriptTarget.Latest, true)
    source.forEachChild((node) => {
      if (!ts.isImportDeclaration(node) || !ts.isStringLiteral(node.moduleSpecifier)) return
      const specifier = node.moduleSpecifier.text
      const relative = path.relative(runtimeRoot, file).replaceAll("\\", "/")
      if (["kernel", "workspace", "security"].includes(area) && /^(?:base-harness$|@base-harness\/(?:core|coordinator|kernel-host|tui|verification)(?:\/|$))/.test(specifier)) {
        errors.push(`${relative}: foundational package cannot depend on execution or policy orchestration`)
      }
      if (area === "coordinator" && (specifier === "base-harness" || specifier.startsWith("@base-harness/core") || specifier.startsWith("@base-harness/tui"))) {
        errors.push(`${relative}: coordinator must use execution ports, not execution package imports`)
      }
      if (area === "tui" && ["workspace", "kernel-host", "security"].some((name) => specifier === `@base-harness/${name}` || specifier.startsWith(`@base-harness/${name}/`))) {
        errors.push(`${relative}: TUI must request policy-owned actions through Host API`)
      }
      if ((area === "host" || area === "tui") && specifier === "@base-harness/core/orchestration") {
        errors.push(`${relative}: orchestration must be accessed through the Host Coordinator facade`)
      }
      if ((area === "host" || area === "tui") && specifier === "@base-harness/verification") {
        errors.push(`${relative}: verification must be accessed through the Host API`)
      }
      if ((area === "host" || area === "tui") && specifier === "@base-harness/coordinator" && file !== facade) {
        errors.push(`${relative}: coordinator may only be imported by the Host facade`)
      }
      if (area === "core" && ["@base-harness/coordinator", "@base-harness/verification", "base-harness"].includes(specifier)) {
        errors.push(`${relative}: core cannot depend on coordinator, verifier, or host`)
      }
      if (area === "verification" && (specifier.startsWith("@base-harness/core") || specifier === "@base-harness/coordinator" || specifier === "base-harness")) {
        errors.push(`${relative}: verifier cannot depend on execution packages`)
      }
    })
  }
}

const packageNames = ["base-harness", "coordinator", "core", "verification", "tui", "kernel", "kernel-host", "workspace", "security"]
const graph = new Map<string, string[]>()
for (const directory of packageNames) {
  const manifest = JSON.parse(await fs.readFile(path.join(packageRoot, directory, "package.json"), "utf8"))
  const name = String(manifest.name)
  const dependencies = { ...(manifest.dependencies ?? {}), ...(manifest.devDependencies ?? {}) }
  graph.set(
    name,
    Object.keys(dependencies).filter((value) =>
      packageNames.some((item) => value === item || value === `@base-harness/${item}`),
    ),
  )
}

const visiting = new Set<string>()
const visited = new Set<string>()
const visit = (name: string, stack: string[]) => {
  if (visiting.has(name)) {
    errors.push(`package cycle: ${[...stack, name].join(" -> ")}`)
    return
  }
  if (visited.has(name)) return
  visiting.add(name)
  for (const dependency of graph.get(name) ?? []) visit(dependency, [...stack, name])
  visiting.delete(name)
  visited.add(name)
}
for (const name of graph.keys()) visit(name, [])

if (errors.length) {
  console.error(errors.join("\n"))
  process.exit(1)
}
console.log("Harness module boundaries are valid.")
