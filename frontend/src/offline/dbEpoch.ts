// Story 7.2: the server's `db_epoch` changes on every restore. The client remembers the
// epoch each Session belongs to (learned from the start-session, bundle and event
// responses) and stamps its outbox events with it; the server refuses events stamped with
// an older epoch (409 STALE_EPOCH) and the client discards them and shows a notice.
// Storage is a per-viewer convenience: localStorage when available, memory otherwise.

const KEY = 'hoctap.sessionEpochs'
const MAX_ENTRIES = 50

const memory = new Map<string, string>()

function readAll(): Record<string, string> {
  try {
    const raw = globalThis.localStorage?.getItem(KEY)
    const parsed: unknown = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, string>) : {}
  } catch {
    return {}
  }
}

/** Remembers the `db_epoch` a Session was created or last seen under. */
export function rememberSessionEpoch(sessionId: string, epoch: string | undefined | null): void {
  if (!epoch) return
  memory.set(sessionId, epoch)
  try {
    const all = readAll()
    delete all[sessionId] // re-insert last so the oldest entries are dropped first
    all[sessionId] = epoch
    const keys = Object.keys(all)
    for (const old of keys.slice(0, Math.max(0, keys.length - MAX_ENTRIES))) delete all[old]
    globalThis.localStorage?.setItem(KEY, JSON.stringify(all))
  } catch {
    // storage blocked or full: the in-memory copy still works for this page load
  }
}

/** The `db_epoch` known for a Session, or undefined (legacy Sessions are unstamped). */
export function epochForSession(sessionId: string): string | undefined {
  return memory.get(sessionId) ?? readAll()[sessionId]
}

// --- "Events from before a restore were dropped" notice -------------------------------

let stale = false
const listeners = new Set<() => void>()

export function noteStaleEpoch(): void {
  stale = true
  listeners.forEach((l) => l())
}

export function dismissStaleEpochNotice(): void {
  stale = false
  listeners.forEach((l) => l())
}

export function subscribeStaleEpoch(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function staleEpochSnapshot(): boolean {
  return stale
}

/** Test-only: forgets everything remembered. */
export function _resetDbEpochForTests(): void {
  memory.clear()
  stale = false
  try {
    globalThis.localStorage?.removeItem(KEY)
  } catch {
    // ignore
  }
}
