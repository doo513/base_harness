import path from "path"

process.env.BASE_HARNESS_DB = ":memory:"
process.env.BASE_HARNESS_MODELS_PATH = path.join(import.meta.dir, "plugin", "fixtures", "models-dev.json")
process.env.BASE_HARNESS_DISABLE_MODELS_FETCH = "true"
