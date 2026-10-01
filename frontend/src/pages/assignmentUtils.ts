import type { AssignmentOut } from '../api/client'

const LOCAL_TZ = 'Asia/Ho_Chi_Minh'

/** Tomorrow's calendar date (YYYY-MM-DD) in Asia/Ho_Chi_Minh, the default assign date. */
export function tomorrowLocal(now: Date = new Date()): string {
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: LOCAL_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now)
  const next = new Date(`${today}T00:00:00Z`)
  next.setUTCDate(next.getUTCDate() + 1)
  return next.toISOString().slice(0, 10)
}

const STATUS_LABEL: Record<string, string> = {
  todo: 'Chưa làm',
  doing: 'Đang làm',
  done: 'Đã xong',
}

export function statusText(a: Pick<AssignmentOut, 'status' | 'part' | 'part_count'>): string {
  const base = STATUS_LABEL[a.status] ?? a.status
  return a.status === 'doing' && a.part != null && a.part_count != null
    ? `${base} (Phần ${a.part}/${a.part_count})`
    : base
}

/**
 * Orchestrator's Independent Audit (spec-4-3 #1, 2026-10-01): a not-done Assignment whose
 * Lesson no longer resolves to any visible Problem (`resolvable: false`) never reaches
 * Home as "Bài hôm nay" -- it would 422 there. The Dashboard still lists it, so Anh needs a
 * plain-language reason to delete it or fix/unhide the Lesson's content, instead of just
 * seeing "Chưa làm" forever with no clue why Bin never seems to get it.
 */
export function unavailableNote(
  a: Pick<AssignmentOut, 'status' | 'resolvable'>,
): string | null {
  return a.status !== 'done' && a.resolvable === false
    ? 'Không có bài nào hiển thị cho bé trong bài học này -- hãy xoá hoặc kiểm tra lại nội dung.'
    : null
}
