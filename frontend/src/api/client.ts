// Thin fetch helpers over the generated OpenAPI types (src/api/schema.d.ts).
// Never hand-write API types: run `npm run gen:api` after backend changes.
import { rememberSessionEpoch } from '../offline/dbEpoch'
import type { components } from './schema'

export type Schemas = components['schemas']
export type Health = Schemas['Health']
export type ErrorResponse = Schemas['ErrorResponse']
export type SetupStatus = Schemas['SetupStatus']
export type SetupRequest = Schemas['SetupRequest']
export type Profile = Schemas['Profile']
export type Avatar = Profile['avatar']
export type ProfileIn = Schemas['ProfileIn']
export type ProfilePatch = Schemas['ProfilePatch']
export type ChangePinRequest = Schemas['ChangePinRequest']
export type LoginRequest = Schemas['LoginRequest']
export type SessionStatus = Schemas['SessionStatus']
export type ProblemSummary = Schemas['ProblemSummary']
export type ProblemPage = Schemas['ProblemPage']
export type ProblemDetail = Schemas['ProblemDetail']
export type ProblemDoc = Schemas['ProblemDoc']
export type ProblemPart = ProblemDoc['parts'][number]
export type ReviewBook = Schemas['ReviewBook']
export type ReportOut = Schemas['ReportOut']
export type EditIn = Schemas['EditIn']
export type OverrideOut = Schemas['OverrideOut']
export type ConceptsOut = Schemas['ConceptsOut']
export type ProposalOut = Schemas['ProposalOut']
export type ConceptOut = Schemas['ConceptOut']
export type GuideDetail = Schemas['GuideDetail']
export type GuideEditIn = Schemas['GuideEditIn']
export type SpotCheckOut = Schemas['SpotCheckOut']
export type SpotCheckItem = Schemas['SpotCheckItem']
export type VerdictIn = Schemas['VerdictIn']
export type GateReport = Schemas['GateReport']
export type ChildProblemView = Schemas['ChildProblemView']
export type LibraryBook = Schemas['LibraryBook']
export type LibraryUnit = Schemas['LibraryUnit']
export type LibraryLesson = Schemas['LibraryLesson']
export type LibraryHomeOut = Schemas['LibraryHomeOut']
export type HomeLessonOut = Schemas['HomeLessonOut']
export type SessionOut = Schemas['SessionOut']
export type LessonRefIn = Schemas['LessonRefIn']
export type ReplayRefIn = Schemas['ReplayRefIn']
export type RetryRefIn = Schemas['RetryRefIn']
export type ConceptRefIn = Schemas['ConceptRefIn']
export type LibraryConcept = Schemas['LibraryConcept']
export type ConceptDetailOut = Schemas['ConceptDetailOut']
export type StartSessionRefIn = LessonRefIn | ReplayRefIn | RetryRefIn | ConceptRefIn
export type BundleOut = Schemas['BundleOut']
export type BundleProblemOut = Schemas['BundleProblemOut']
export type EventIn = Schemas['EventIn']
export type EventOut = Schemas['EventOut']
export type SummaryOut = Schemas['SummaryOut']
export type QuizResultOut = Schemas['QuizResultOut']
export type BadgeOut = Schemas['BadgeOut']
export type BadgeKey = BadgeOut['badge_key']
export type DashboardOut = Schemas['DashboardOut']
export type AssignmentOut = Schemas['AssignmentOut']
export type AssignmentIn = Schemas['AssignmentIn']
export type HomeAssignmentOut = Schemas['HomeAssignmentOut']
export type RestoreOut = Schemas['RestoreOut']
export type WorksheetOut = Schemas['WorksheetOut']
export type WorksheetProblem = Schemas['WorksheetProblem']

export const API_BASE = '/api/v1'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  /** Extra messages from the envelope, e.g. the validation errors of a refused edit. */
  readonly details: string[]

  constructor(status: number, code: string, message: string, details: string[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }
}

/** Story 2.11: a genuinely unreachable server (`fetch()` itself threw -- e.g. a real
 * browser's `TypeError: Failed to fetch`, or a timeout/abort), as opposed to `ApiError`
 * (the server responded, just with a 4xx/5xx). Only THIS distinguishes "queue it for the
 * offline outbox" from "surface a normal error" -- see `offline/outbox.ts`. */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('Không có kết nối mạng.')
    this.name = 'NetworkError'
    this.cause = cause
  }
}

/** Review Triage Log #8 (2026-10-01, high): a TCP-connected-but-never-responding server
 * (a stalled captive portal, a flaky school Wi-Fi proxy -- exactly the real-world condition
 * Story 2.11 exists to survive) previously left `fetch()` never settling at all, since
 * nothing here ever aborted it -- the submit UI (`PartPlayer.handleCheck()`) got stuck in
 * `phase: 'submitting'` forever: no offline screen, no error, no retry, just a dead button.
 * 12s is a judgment call for a LAN app (this server is always on the same Wi-Fi as the
 * tablet, never over the public internet) -- long enough that a merely slow SQLite write
 * under WAL contention isn't mistaken for a dead connection, short enough that a genuinely
 * stalled connection resolves well within a young child's patience. */
const REQUEST_TIMEOUT_MS = 12_000

function isJson(resp: Response): boolean {
  return (resp.headers.get('content-type') ?? '').includes('json')
}

async function throwApiError(resp: Response): Promise<never> {
  let body: Partial<ErrorResponse> | undefined
  try {
    body = isJson(resp) ? ((await resp.json()) as Partial<ErrorResponse>) : undefined
  } catch {
    body = undefined
  }
  throw new ApiError(
    resp.status,
    body?.error?.code ?? 'HTTP_ERROR',
    body?.error?.message ?? resp.statusText,
    body?.error?.details ?? [],
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')
  // `AbortSignal.any()` combines the timeout with any caller-supplied signal (e.g. a
  // query's own unmount-cancellation) -- whichever fires first aborts the fetch, and either
  // way the resulting `AbortError` is caught just below and wrapped the same as any other
  // unreachable-server failure.
  const signal = init?.signal
    ? AbortSignal.any([init.signal, AbortSignal.timeout(REQUEST_TIMEOUT_MS)])
    : AbortSignal.timeout(REQUEST_TIMEOUT_MS)
  let resp: Response
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...init, headers, signal })
  } catch (err) {
    // The server never answered at all (DNS/TCP failure, offline, or -- Review Triage Log
    // #8 -- a timeout: `AbortSignal.timeout()` rejects `fetch()` with a `TimeoutError`
    // `DOMException`, structurally identical to any other abort) -- never an `ApiError`,
    // which requires an actual HTTP response to read a status/body from.
    throw new NetworkError(err)
  }
  if (!resp.ok) await throwApiError(resp)
  if (resp.status === 204 || !isJson(resp)) return undefined as T
  return (await resp.json()) as T
}

export function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, method: 'GET' })
}

function sendJson<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (body !== undefined && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  return request<T>(path, {
    ...init,
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
}

/** POSTs `body` as JSON (omit it for an empty body). */
export function apiPost<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  return sendJson<T>('POST', path, body, init)
}

export function apiPut<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return sendJson<T>('PUT', path, body, init)
}

export function apiPatch<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  return sendJson<T>('PATCH', path, body, init)
}

export function apiDelete<T>(path: string, init?: RequestInit): Promise<T> {
  return request<T>(path, { ...init, method: 'DELETE' })
}

export function getHealth(signal?: AbortSignal): Promise<Health> {
  return apiGet<Health>('/health', { signal })
}

export function getSetupStatus(signal?: AbortSignal): Promise<SetupStatus> {
  return apiGet<SetupStatus>('/setup/status', { signal })
}

export function completeSetup(body: SetupRequest): Promise<Profile> {
  return apiPost<Profile>('/setup', body)
}

export function parentLogin(body: LoginRequest): Promise<void> {
  return apiPost<void>('/parent/login', body)
}

export function parentLogout(): Promise<void> {
  return apiPost<void>('/parent/logout')
}

export function getParentSession(signal?: AbortSignal): Promise<SessionStatus> {
  return apiGet<SessionStatus>('/parent/session', { signal })
}

export function getProfiles(signal?: AbortSignal): Promise<Profile[]> {
  return apiGet<Profile[]>('/profiles', { signal })
}

// --- Profiles and settings (Story 4.1) -------------------------------------------------

export function createProfile(body: ProfileIn): Promise<Profile> {
  return apiPost<Profile>('/profiles', body)
}

export function updateProfile(id: string, body: ProfilePatch): Promise<Profile> {
  return apiPatch<Profile>(`/profiles/${encodeURIComponent(id)}`, body)
}

export function deleteProfile(id: string): Promise<void> {
  return apiDelete<void>(`/profiles/${encodeURIComponent(id)}`)
}

export function changeParentPin(body: ChangePinRequest): Promise<void> {
  return apiPost<void>('/parent/pin', body)
}

// --- Badges (Story 3.2) ----------------------------------------------------------------

/** All 3 fixed badges (`week1`/`streak7`/`stars100`) with `earned`/`earned_at` -- the
 * "Huy hiệu của em" screen's full state. */
export function getProfileBadges(profileId: string, signal?: AbortSignal): Promise<BadgeOut[]> {
  return apiGet<BadgeOut[]>(`/profiles/${enc(profileId)}/badges`, { signal })
}

// --- Progress dashboard (Story 4.2) ----------------------------------------------------

export function getParentDashboard(profileId: string, signal?: AbortSignal): Promise<DashboardOut> {
  return apiGet<DashboardOut>(`/parent/dashboard/${enc(profileId)}`, { signal })
}

// --- Assignments (Story 4.3) -----------------------------------------------------------

export function getAssignments(profileId: string, signal?: AbortSignal): Promise<AssignmentOut[]> {
  return apiGet<AssignmentOut[]>(`/parent/assignments?profile_id=${encodeURIComponent(profileId)}`, {
    signal,
  })
}

export function createAssignment(body: AssignmentIn): Promise<AssignmentOut> {
  return apiPost<AssignmentOut>('/parent/assignments', body)
}

export function deleteAssignment(id: string): Promise<void> {
  return apiDelete<void>(`/parent/assignments/${encodeURIComponent(id)}`)
}

// --- Child Library (Sách, Story 2.3) ------------------------------------------------

const LIBRARY = '/library'

export function getLibraryBooks(
  grade: number,
  profileId?: string,
  signal?: AbortSignal,
): Promise<LibraryBook[]> {
  const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : ''
  return apiGet<LibraryBook[]>(`${LIBRARY}/grades/${grade}/books${query}`, { signal })
}

export function getLibraryLesson(
  bookId: string,
  unitKey: string,
  lessonKey: string,
  signal?: AbortSignal,
): Promise<ChildProblemView[]> {
  return apiGet<ChildProblemView[]>(
    `${LIBRARY}/lessons/${encodeURIComponent(bookId)}/${encodeURIComponent(unitKey)}/${encodeURIComponent(lessonKey)}`,
    { signal },
  )
}

export function getLibraryConcepts(grade: number, signal?: AbortSignal): Promise<LibraryConcept[]> {
  return apiGet<LibraryConcept[]>(`${LIBRARY}/concepts?grade=${grade}`, { signal })
}

export function getLibraryConcept(
  conceptId: string,
  signal?: AbortSignal,
): Promise<ConceptDetailOut> {
  return apiGet<ConceptDetailOut>(`${LIBRARY}/concepts/${encodeURIComponent(conceptId)}`, {
    signal,
  })
}

export function getLibraryHome(profileId: string, signal?: AbortSignal): Promise<LibraryHomeOut> {
  return apiGet<LibraryHomeOut>(`${LIBRARY}/home/${encodeURIComponent(profileId)}`, { signal })
}

// --- Sessions (Story 2.4) ------------------------------------------------------------

const SESSIONS = '/sessions'

/** Starts a Session. `mode` (Story 2.10) defaults to `"practice"` server-side when
 * omitted; the "Luyện lại bài sai" flow passes `{kind: "replay", source_session_id}` and
 * `mode: "replay"` together. */
export function startSession(
  profileId: string,
  ref: StartSessionRefIn,
  mode?: 'practice' | 'replay' | 'retry' | 'concept',
  assignmentId?: string,
): Promise<SessionOut> {
  return apiPost<SessionOut>(SESSIONS, {
    profile_id: profileId,
    ref,
    mode,
    assignment_id: assignmentId,
  }).then((session) => {
    rememberSessionEpoch(session.id, session.db_epoch)
    return session
  })
}

export function getSessionSummary(
  sessionId: string,
  profileId: string,
  signal?: AbortSignal,
): Promise<SummaryOut> {
  return apiGet<SummaryOut>(
    `${SESSIONS}/${enc(sessionId)}/summary?profile_id=${encodeURIComponent(profileId)}`,
    { signal },
  )
}

export function getSessionBundle(
  sessionId: string,
  profileId: string,
  chunk: number,
  signal?: AbortSignal,
): Promise<BundleOut> {
  return apiGet<BundleOut>(
    `${SESSIONS}/${enc(sessionId)}/bundle?profile_id=${encodeURIComponent(profileId)}&chunk=${chunk}`,
    { signal },
  ).then((bundle) => {
    rememberSessionEpoch(sessionId, bundle.db_epoch)
    return bundle
  })
}

export function postSessionEvents(
  sessionId: string,
  profileId: string,
  events: EventIn[],
): Promise<EventOut[]> {
  return apiPost<EventOut[]>(`${SESSIONS}/${enc(sessionId)}/events`, {
    profile_id: profileId,
    events,
  }).then((out) => {
    rememberSessionEpoch(sessionId, out[0]?.db_epoch)
    return out
  })
}

// --- Backup and restore (Story 7.2) ------------------------------------------------

/** POSTs for the verified `.db` backup; returns the bytes and the server's file name. */
export async function downloadBackup(): Promise<{ blob: Blob; filename: string }> {
  let resp: Response
  try {
    resp = await fetch(`${API_BASE}/parent/backup`, { method: 'POST' })
  } catch (err) {
    throw new NetworkError(err)
  }
  if (!resp.ok) await throwApiError(resp)
  const match = /filename="?([^";]+)"?/.exec(resp.headers.get('content-disposition') ?? '')
  return { blob: await resp.blob(), filename: match?.[1] ?? 'hoctap-backup.db' }
}

/** Uploads a backup and restores it; `confirm` is the typed phrase. */
export function restoreBackup(file: File, confirm: string): Promise<RestoreOut> {
  const form = new FormData()
  form.append('file', file)
  form.append('confirm', confirm)
  return request<RestoreOut>('/parent/restore', { method: 'POST', body: form })
}

// --- Content Review (Duyệt nội dung) ---------------------------------------------

const REVIEW = '/parent/review'
const enc = encodeURIComponent

export function getReviewQueue(signal?: AbortSignal): Promise<ProblemSummary[]> {
  return apiGet<ProblemSummary[]>(`${REVIEW}/queue`, { signal })
}

export function getReviewBooks(signal?: AbortSignal): Promise<ReviewBook[]> {
  return apiGet<ReviewBook[]>(`${REVIEW}/books`, { signal })
}

export type ProblemFilter = { bookId?: string; unitKey?: string; lessonKey?: string; page?: number }

export function getReviewProblems(filter: ProblemFilter, signal?: AbortSignal): Promise<ProblemPage> {
  const params = new URLSearchParams()
  if (filter.bookId) params.set('book_id', filter.bookId)
  if (filter.unitKey) params.set('unit_key', filter.unitKey)
  if (filter.lessonKey) params.set('lesson_key', filter.lessonKey)
  if (filter.page && filter.page > 1) params.set('page', String(filter.page))
  const query = params.toString()
  return apiGet<ProblemPage>(`${REVIEW}/problems${query ? `?${query}` : ''}`, { signal })
}

export function getReviewProblem(problemId: string, signal?: AbortSignal): Promise<ProblemDetail> {
  return apiGet<ProblemDetail>(`${REVIEW}/problems/${enc(problemId)}`, { signal })
}

export function saveOverrides(problemId: string, edits: EditIn[]): Promise<ProblemDetail> {
  return apiPut<ProblemDetail>(`${REVIEW}/problems/${enc(problemId)}/overrides`, { edits })
}

export function deleteOverride(problemId: string, overrideId: string): Promise<ProblemDetail> {
  return apiDelete<ProblemDetail>(
    `${REVIEW}/problems/${enc(problemId)}/overrides/${enc(overrideId)}`,
  )
}

export function deleteAllOverrides(problemId: string): Promise<ProblemDetail> {
  return apiDelete<ProblemDetail>(`${REVIEW}/problems/${enc(problemId)}/overrides`)
}

/** Duyệt: `contentHash` is the effective hash on screen; a newer one gives 409 STALE. */
export function approveProblem(problemId: string, contentHash: string): Promise<ProblemDetail> {
  return apiPost<ProblemDetail>(`${REVIEW}/problems/${enc(problemId)}/approve`, {
    content_hash: contentHash,
  })
}

export function setProblemHidden(problemId: string, hidden: boolean): Promise<ProblemDetail> {
  return apiPost<ProblemDetail>(`${REVIEW}/problems/${enc(problemId)}/${hidden ? 'hide' : 'unhide'}`)
}

export function reportProblem(problemId: string, note: string): Promise<Schemas['ReportOut']> {
  return apiPost<Schemas['ReportOut']>(`${REVIEW}/problems/${enc(problemId)}/reports`, { note })
}

export function flagProblem(problemId: string, profileId: string): Promise<void> {
  return apiPost<void>(`/problems/${enc(problemId)}/flag`, { profile_id: profileId })
}

export function resolveReport(reportId: string): Promise<Schemas['ReportOut']> {
  return apiPost<Schemas['ReportOut']>(`${REVIEW}/reports/${enc(reportId)}/resolve`)
}

export function getConcepts(signal?: AbortSignal): Promise<ConceptsOut> {
  return apiGet<ConceptsOut>(`${REVIEW}/concepts`, { signal })
}

export function acceptProposal(body: Schemas['AcceptIn']): Promise<ConceptsOut> {
  return apiPost<ConceptsOut>(`${REVIEW}/concepts/accept`, body)
}

export function mergeProposal(body: Schemas['MergeIn']): Promise<ConceptsOut> {
  return apiPost<ConceptsOut>(`${REVIEW}/concepts/merge`, body)
}

export function renameConcept(body: Schemas['RenameIn']): Promise<ConceptsOut> {
  return apiPost<ConceptsOut>(`${REVIEW}/concepts/rename`, body)
}

// --- Hướng dẫn khái niệm (Concept Guide) ------------------------------------------

const guidePath = (conceptId: string) => `${REVIEW}/concepts/${enc(conceptId)}/guide`

export function getConceptGuide(conceptId: string, signal?: AbortSignal): Promise<GuideDetail> {
  return apiGet<GuideDetail>(guidePath(conceptId), { signal })
}

export function saveConceptGuide(conceptId: string, edits: GuideEditIn[]): Promise<GuideDetail> {
  return apiPut<GuideDetail>(guidePath(conceptId), { edits })
}

export function resetConceptGuide(conceptId: string): Promise<GuideDetail> {
  return apiDelete<GuideDetail>(guidePath(conceptId))
}

export function approveConceptGuide(conceptId: string, contentHash: string): Promise<GuideDetail> {
  return apiPost<GuideDetail>(`${guidePath(conceptId)}/approve`, { content_hash: contentHash })
}

// --- Kiểm tra ngẫu nhiên (spot-check) --------------------------------------------

export function getSpotCheck(signal?: AbortSignal): Promise<SpotCheckOut> {
  return apiGet<SpotCheckOut>(`${REVIEW}/spot-check`, { signal })
}

/** Rút mẫu mới: a new sample; the old one is kept for history. */
export function drawSpotCheck(): Promise<SpotCheckOut> {
  return apiPost<SpotCheckOut>(`${REVIEW}/spot-check/draw`)
}

/** Đúng / Sai; `content_hash` is the effective hash on screen (a newer one gives 409 STALE). */
export function setSpotCheckVerdict(
  sampleId: string,
  problemId: string,
  body: VerdictIn,
): Promise<SpotCheckOut> {
  return apiPut<SpotCheckOut>(`${REVIEW}/spot-check/${enc(sampleId)}/items/${enc(problemId)}`, body)
}

// --- Go/no-go gate (Chạy thử & đánh giá) -------------------------------------------

export function getGate(signal?: AbortSignal): Promise<GateReport> {
  return apiGet<GateReport>('/build/gate', { signal })
}

export function approveGate(estCostSeen: number): Promise<GateReport> {
  return apiPost<GateReport>('/build/gate/approve', { accept_cost: true, est_cost_seen: estCostSeen })
}

export function revokeGate(): Promise<GateReport> {
  return apiPost<GateReport>('/build/gate/revoke')
}

// --- Extraction control / Chạy thử (Story 1.10) ------------------------------------

export type CatalogueBook = Schemas['CatalogueBookOut']
export type BuildRun = Schemas['RunOut']

export function getCatalogueBooks(signal?: AbortSignal): Promise<CatalogueBook[]> {
  return apiGet<CatalogueBook[]>('/build/books', { signal })
}

export function getCurrentRun(signal?: AbortSignal): Promise<BuildRun | null> {
  return apiGet<BuildRun | null>('/build/runs/current', { signal })
}

export function startRun(bookId: string, pages: string, yesSpend: boolean): Promise<BuildRun> {
  return apiPost<BuildRun>('/build/runs', { book_id: bookId, pages, yes_spend: yesSpend })
}

export function pauseRun(runId: string): Promise<BuildRun> {
  return apiPost<BuildRun>(`/build/runs/${enc(runId)}/pause`)
}

export function resumeRun(runId: string): Promise<BuildRun> {
  return apiPost<BuildRun>(`/build/runs/${enc(runId)}/resume`)
}

export function cancelRun(runId: string): Promise<BuildRun> {
  return apiPost<BuildRun>(`/build/runs/${enc(runId)}/cancel`)
}

// --- Full-corpus run / Chạy toàn bộ (Story 6.2) ------------------------------------

export type FullPlan = Schemas['FullPlanOut']
export type FullRun = Schemas['FullRunOut']

export function planFullRun(grade: number | null = null): Promise<FullPlan> {
  return apiPost<FullPlan>('/build/full/plan', { grade, books: [] })
}

export function getCurrentFullRun(signal?: AbortSignal): Promise<FullRun | null> {
  return apiGet<FullRun | null>('/build/full/current', { signal })
}

export function startFullRun(
  maxTotalUsd: number,
  yesSpend: boolean,
  grade: number | null = null,
): Promise<FullRun | null> {
  return apiPost<FullRun | null>('/build/full', {
    grade,
    books: [],
    max_total_usd: maxTotalUsd,
    yes_spend: yesSpend,
  })
}

// --- Printable worksheets (Story 7.1): parent-only, carries the Answer Keys -------------

export type WorksheetRef =
  | { bookId: string; unitKey: string; lessonKey: string }
  | { conceptId: string; profileId: string }

export function getWorksheet(ref: WorksheetRef, signal?: AbortSignal): Promise<WorksheetOut> {
  const params = new URLSearchParams(
    'conceptId' in ref
      ? { concept_id: ref.conceptId, profile_id: ref.profileId }
      : { book_id: ref.bookId, unit_key: ref.unitKey, lesson_key: ref.lessonKey },
  )
  return apiGet<WorksheetOut>(`/parent/worksheet?${params.toString()}`, { signal })
}
