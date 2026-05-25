export type SnapshotPayload<T> = {
  version: 1
  savedAt: string
  data: T
}

export function readSnapshot<T>(
  key: string,
  fallback: T,
  validate?: (value: unknown) => value is T,
): SnapshotPayload<T> | null {
  if (typeof window === "undefined") {
    return null
  }

  const raw = window.localStorage.getItem(key)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<SnapshotPayload<unknown>>

    if (parsed.version !== 1 || typeof parsed.savedAt !== "string") {
      return null
    }

    const data = parsed.data

    if (validate && !validate(data)) {
      return null
    }

    return {
      version: 1,
      savedAt: parsed.savedAt,
      data: (validate ? data : data ?? fallback) as T,
    }
  } catch {
    return null
  }
}

export function writeSnapshot<T>(key: string, data: T) {
  if (typeof window === "undefined") {
    return
  }

  const payload: SnapshotPayload<T> = {
    version: 1,
    savedAt: new Date().toISOString(),
    data,
  }

  try {
    window.localStorage.setItem(key, JSON.stringify(payload))
  } catch {
    // Ignore storage quota or private-mode failures.
  }
}

export function removeSnapshot(key: string) {
  if (typeof window === "undefined") {
    return
  }

  try {
    window.localStorage.removeItem(key)
  } catch {
    // Ignore storage failures.
  }
}
