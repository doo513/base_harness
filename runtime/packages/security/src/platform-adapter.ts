export type ProcessContainment = "job_object" | "tree_kill" | "process_group"

export const WINDOWS_JOB_OBJECT_ENV = "BASE_HARNESS_INTERNAL_WINDOWS_JOB_OBJECT"

export interface WindowsJobHandle {
  readonly containment: "job_object"
  close(): void
}

export async function assignWindowsJobObject(pid: number): Promise<WindowsJobHandle | undefined> {
  if (process.platform !== "win32" || !pid) return undefined
  try {
    const ffi = (await import("bun:ffi")) as any
    const type = ffi.FFIType
    const kernel = ffi.dlopen("kernel32.dll", {
      CreateJobObjectW: { args: [type.ptr, type.ptr], returns: type.ptr },
      OpenProcess: { args: [type.u32, type.u32, type.u32], returns: type.ptr },
      SetInformationJobObject: { args: [type.ptr, type.u32, type.ptr, type.u32], returns: type.u32 },
      AssignProcessToJobObject: { args: [type.ptr, type.ptr], returns: type.u32 },
      CloseHandle: { args: [type.ptr], returns: type.u32 },
    })
    const symbols = kernel.symbols as Record<string, (...args: any[]) => any>
    const job = symbols.CreateJobObjectW!(0, 0)
    if (!job) {
      kernel.close()
      return undefined
    }
    const processHandle = symbols.OpenProcess!(0x0001 | 0x0100 | 0x0400, 0, pid)
    if (!processHandle) {
      symbols.CloseHandle!(job)
      kernel.close()
      return undefined
    }
    const information = new Uint8Array(144)
    new DataView(information.buffer).setUint32(16, 0x00002000, true)
    const configured = symbols.SetInformationJobObject!(job, 9, ffi.ptr(information), information.byteLength)
    const assigned = configured ? symbols.AssignProcessToJobObject!(job, processHandle) : 0
    symbols.CloseHandle!(processHandle)
    if (!assigned) {
      symbols.CloseHandle!(job)
      kernel.close()
      return undefined
    }
    let closed = false
    return {
      containment: "job_object",
      close() {
        if (closed) return
        closed = true
        symbols.CloseHandle!(job)
        kernel.close()
      },
    }
  } catch {
    return undefined
  }
}

