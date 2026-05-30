export type SnapshotPayload<T> = {
  version: 1
  savedAt: string
  data: T
  isStale?: boolean
  ageMs?: number
}

export type SnapshotReadOptions = {
  maxAgeMs?: number
  removeInvalid?: boolean
}

export const SNAPSHOT_MAX_AGE_MS = {
  calendar: 10 * 60 * 1000,
  memories: 30 * 60 * 1000,
  goals: 60 * 60 * 1000,
  people: 6 * 60 * 60 * 1000,
} as const


export function sanitizeSnapshotKeyPart(value: string): string {
  return value
    .trim()
    .replace(/[^a-zA-Z0-9._-]+/g, "_")
    .replace(/^_+|_+$/g, "")
}

export function userScopedSnapshotKey({
  userId,
  area,
  version = "v1",
  detail,
}: {
  userId: string
  area: string
  version?: string
  detail?: string
}): string {
  const safeUserId = sanitizeSnapshotKeyPart(userId)
  const safeArea = sanitizeSnapshotKeyPart(area)
  const safeVersion = sanitizeSnapshotKeyPart(version)
  const safeDetail = detail ? sanitizeSnapshotKeyPart(detail) : null

  if (!safeUserId) {
    throw new Error("userScopedSnapshotKey requires a userId")
  }

  if (!safeArea) {
    throw new Error("userScopedSnapshotKey requires an area")
  }

  return safeDetail
    ? `app:snapshot:${safeUserId}:${safeArea}:${safeDetail}:${safeVersion}`
    : `app:snapshot:${safeUserId}:${safeArea}:${safeVersion}`
}

export function userScopedSnapshotPrefix(userId: string): string {
  const safeUserId = sanitizeSnapshotKeyPart(userId)

  if (!safeUserId) {
    throw new Error("userScopedSnapshotPrefix requires a userId")
  }

  return `app:snapshot:${safeUserId}:`
}

export function clearUserScopedSnapshots(userId: string): number {
  return clearSnapshotsByPrefix(userScopedSnapshotPrefix(userId))
}


function nowMs(): number {
  return Date.now()
}

function parseSavedAt(value: unknown): number | null {
  if (typeof value !== "string") {
    return null
  }

  const parsed = new Date(value).getTime()
  return Number.isNaN(parsed) ? null : parsed
}

export function getSnapshotAgeMs(savedAt: string | null | undefined): number | null {
  const savedAtMs = parseSavedAt(savedAt)
  if (savedAtMs == null) {
    return null
  }

  return Math.max(0, nowMs() - savedAtMs)
}

export function isSnapshotStale(
  savedAt: string | null | undefined,
  maxAgeMs?: number,
): boolean {
  if (!maxAgeMs || maxAgeMs <= 0) {
    return false
  }

  const ageMs = getSnapshotAgeMs(savedAt)
  if (ageMs == null) {
    return true
  }

  return ageMs > maxAgeMs
}

export function readSnapshot<T>(
  key: string,
  fallback: T,
  validate?: (value: unknown) => value is T,
  options: SnapshotReadOptions = {},
): SnapshotPayload<T> | null {
  if (typeof window === "undefined") {
    return null
  }

  const raw = window.localStorage.getItem(key)
  if (!raw) {
    return null
  }

  const shouldRemoveInvalid = options.removeInvalid ?? true

  try {
    const parsed = JSON.parse(raw) as Partial<SnapshotPayload<unknown>>

    if (parsed.version !== 1 || typeof parsed.savedAt !== "string") {
      if (shouldRemoveInvalid) {
        window.localStorage.removeItem(key)
      }
      return null
    }

    const data = parsed.data

    if (validate && !validate(data)) {
      if (shouldRemoveInvalid) {
        window.localStorage.removeItem(key)
      }
      return null
    }

    const resolvedData = (validate ? data : data ?? fallback) as T
    const ageMs = getSnapshotAgeMs(parsed.savedAt)
    const isStale = isSnapshotStale(parsed.savedAt, options.maxAgeMs)

    return {
      version: 1,
      savedAt: parsed.savedAt,
      data: resolvedData,
      isStale,
      ageMs: ageMs ?? undefined,
    }
  } catch {
    if (shouldRemoveInvalid) {
      try {
        window.localStorage.removeItem(key)
      } catch {
        // Ignore storage failures.
      }
    }
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

export type PromoteSnapshotOptions<T> = {
  fromKey: string
  toKey: string
  fallback: T
  validate?: (value: unknown) => value is T
  options?: SnapshotReadOptions
  removeLegacy?: boolean
}

/**
 * Prefer a user-scoped snapshot, but safely promote an older legacy snapshot
 * into the scoped key when the scoped cache is not available yet.
 */
export function promoteSnapshot<T>({
  fromKey,
  toKey,
  fallback,
  validate,
  options,
  removeLegacy = false,
}: PromoteSnapshotOptions<T>): SnapshotPayload<T> | null {
  const existing = readSnapshot<T>(toKey, fallback, validate, options)
  if (existing || fromKey === toKey) {
    return existing
  }

  const legacy = readSnapshot<T>(fromKey, fallback, validate, options)
  if (!legacy) {
    return null
  }

  writeSnapshot(toKey, legacy.data)

  if (removeLegacy) {
    removeSnapshot(fromKey)
  }

  return legacy
}

export function getSnapshotSavedAt(key: string): string | null {
  if (typeof window === "undefined") {
    return null
  }

  const raw = window.localStorage.getItem(key)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw) as Partial<SnapshotPayload<unknown>>
    return typeof parsed.savedAt === "string" ? parsed.savedAt : null
  } catch {
    try {
      window.localStorage.removeItem(key)
    } catch {
      // Ignore storage failures.
    }
    return null
  }
}

export function clearSnapshotsByPrefix(prefix: string): number {
  if (typeof window === "undefined") {
    return 0
  }

  const keysToRemove: string[] = []

  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index)
    if (key?.startsWith(prefix)) {
      keysToRemove.push(key)
    }
  }

  for (const key of keysToRemove) {
    try {
      window.localStorage.removeItem(key)
    } catch {
      // Ignore storage failures.
    }
  }

  return keysToRemove.length
}

export function clearKnownAppSnapshots(): number {
  const exactKeys = [
    "app:people-snapshot:v1",
    "app:calendar-events-cache:v1",
    "app:memories-snapshot:v1",
  ]

  let removed = 0

  for (const key of exactKeys) {
    if (getSnapshotSavedAt(key)) {
      removeSnapshot(key)
      removed += 1
    }
  }

  removed += clearSnapshotsByPrefix("app:goals-snapshot:v1:")

  // Future user-scoped snapshots use app:snapshot:<userId>:...
  // They should normally be cleared with clearUserScopedSnapshots(userId).
  // This fallback is intentionally broad for legacy sign-out cleanup.
  removed += clearSnapshotsByPrefix("app:snapshot:")

  return removed
}
