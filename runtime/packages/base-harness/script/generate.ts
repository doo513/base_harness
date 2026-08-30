import path from "path"
import { fileURLToPath } from "url"

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const dir = path.resolve(__dirname, "..")

process.chdir(dir)

const defaultModelsPath = path.resolve(__dirname, "../../core/src/models-catalog.json")
export const modelsData = await Bun.file(process.env.MODELS_DEV_API_JSON ?? defaultModelsPath).text()
console.log("Loaded Base Harness local model catalog")
