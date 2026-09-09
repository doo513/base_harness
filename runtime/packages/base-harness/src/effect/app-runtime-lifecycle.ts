/** Cleanup registration has no runtime imports and never starts services. */
export function createRuntimeFinalizer() {
  let callback: (() => Promise<void>) | undefined
  let pending: Promise<void> | undefined
  return {
    register(value: () => Promise<void>) {
      if (callback && callback !== value) throw new Error("Runtime finalizer is already registered")
      callback = value
    },
    dispose(): Promise<void> {
      if (!callback) return Promise.resolve()
      return pending ??= Promise.resolve().then(callback)
    },
  }
}

export const appRuntimeFinalizer = createRuntimeFinalizer()
