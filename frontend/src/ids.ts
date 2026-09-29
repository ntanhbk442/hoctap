// A client-generated event id for `POST /sessions/{id}/events` (Story 2.4's `EventIn.id`):
// the backend's `_is_uuid7()` (`backend/hoctap/api/sessions.py`) requires a real UUIDv7 (RFC
// 9562 §5.7) -- time-ordered, version nibble `7`, variant bits `10` -- not just any random
// UUID, so a plain `crypto.randomUUID()` (UUIDv4) would be rejected with a 422.
export function newEventId(): string {
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)

  const ts = Date.now() // unix_ts_ms, 48 bits
  bytes[0] = (ts / 2 ** 40) & 0xff
  bytes[1] = (ts / 2 ** 32) & 0xff
  bytes[2] = (ts / 2 ** 24) & 0xff
  bytes[3] = (ts / 2 ** 16) & 0xff
  bytes[4] = (ts / 2 ** 8) & 0xff
  bytes[5] = ts & 0xff

  bytes[6] = 0x70 | (bytes[6] & 0x0f) // version 7
  bytes[8] = 0x80 | (bytes[8] & 0x3f) // variant 10

  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
