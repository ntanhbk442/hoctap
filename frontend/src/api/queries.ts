import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  type EventIn,
  getCatalogueBooks,
  getConcepts,
  getCurrentRun,
  getGate,
  getHealth,
  getLibraryBooks,
  getLibraryHome,
  getLibraryLesson,
  getParentSession,
  getProfiles,
  getReviewBooks,
  getReviewProblem,
  getReviewProblems,
  getReviewQueue,
  getSessionBundle,
  getSessionSummary,
  getSetupStatus,
  getSpotCheck,
  type ProblemFilter,
  startSession,
  type StartSessionRefIn,
} from './client'
import { defaultOutboxStore, postEventsOrQueue } from '../offline/outbox'

// A run polled while it is active (running/pausing); polling stops once it settles.
const ACTIVE_RUN_STATUSES = new Set(['running', 'pausing'])

export const queryKeys = {
  health: ['health'] as const,
  setupStatus: ['setup-status'] as const,
  parentSession: ['parent-session'] as const,
  review: ['review'] as const,
  reviewQueue: ['review', 'queue'] as const,
  reviewBooks: ['review', 'books'] as const,
  reviewProblems: (filter: ProblemFilter) => ['review', 'problems', filter] as const,
  reviewProblem: (problemId: string) => ['review', 'problem', problemId] as const,
  reviewConcepts: ['review', 'concepts'] as const,
  spotCheck: ['review', 'spot-check'] as const,
  gate: ['build', 'gate'] as const,
  catalogueBooks: ['build', 'books'] as const,
  currentRun: ['build', 'runs', 'current'] as const,
  profiles: ['profiles'] as const,
  libraryBooks: (grade: number, profileId?: string) =>
    ['library', 'books', grade, profileId] as const,
  libraryLesson: (bookId: string, unitKey: string, lessonKey: string) =>
    ['library', 'lesson', bookId, unitKey, lessonKey] as const,
  libraryHome: (profileId: string) => ['library', 'home', profileId] as const,
  sessionBundle: (sessionId: string, profileId: string, chunk: number) =>
    ['sessions', sessionId, 'bundle', profileId, chunk] as const,
  sessionSummary: (sessionId: string, profileId: string) =>
    ['sessions', sessionId, 'summary', profileId] as const,
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth(signal),
  })
}

export function useSetupStatus() {
  return useQuery({
    queryKey: queryKeys.setupStatus,
    queryFn: ({ signal }) => getSetupStatus(signal),
  })
}

export function useParentSession() {
  return useQuery({
    queryKey: queryKeys.parentSession,
    queryFn: ({ signal }) => getParentSession(signal),
    // A 401/403 is an answer, not a transient failure.
    retry: false,
    // Re-check when the parent comes back to the tab, so an idle-expired
    // session sends them to the login screen.
    refetchOnWindowFocus: true,
  })
}

export function useReviewQueue() {
  return useQuery({
    queryKey: queryKeys.reviewQueue,
    queryFn: ({ signal }) => getReviewQueue(signal),
  })
}

export function useReviewBooks() {
  return useQuery({
    queryKey: queryKeys.reviewBooks,
    queryFn: ({ signal }) => getReviewBooks(signal),
  })
}

export function useReviewProblems(filter: ProblemFilter) {
  return useQuery({
    queryKey: queryKeys.reviewProblems(filter),
    queryFn: ({ signal }) => getReviewProblems(filter, signal),
    // Keep the current page on screen while the next one loads.
    placeholderData: keepPreviousData,
  })
}

export function useReviewProblem(problemId: string) {
  return useQuery({
    queryKey: queryKeys.reviewProblem(problemId),
    queryFn: ({ signal }) => getReviewProblem(problemId, signal),
  })
}

export function useConcepts() {
  return useQuery({
    queryKey: queryKeys.reviewConcepts,
    queryFn: ({ signal }) => getConcepts(signal),
  })
}

export function useSpotCheck() {
  return useQuery({
    queryKey: queryKeys.spotCheck,
    queryFn: ({ signal }) => getSpotCheck(signal),
  })
}

export function useGate() {
  return useQuery({
    queryKey: queryKeys.gate,
    queryFn: ({ signal }) => getGate(signal),
  })
}

export function useCatalogueBooks() {
  return useQuery({
    queryKey: queryKeys.catalogueBooks,
    queryFn: ({ signal }) => getCatalogueBooks(signal),
  })
}

export function useProfiles() {
  return useQuery({
    queryKey: queryKeys.profiles,
    queryFn: ({ signal }) => getProfiles(signal),
  })
}

/** Books/Units/Lessons of one Grade, each Lesson's visible-Problem count (Story 2.3's
 * Library) and, when `profileId` is given, its real "attempted at least once" numerator
 * (Story 2.4). `enabled: false` until the current Profile's Grade is known. */
export function useLibraryBooks(
  grade: number,
  profileId?: string,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.libraryBooks(grade, profileId),
    queryFn: ({ signal }) => getLibraryBooks(grade, profileId, signal),
    enabled: options.enabled ?? true,
  })
}

export function useLibraryLesson(
  bookId: string,
  unitKey: string,
  lessonKey: string,
  options: { enabled?: boolean } = {},
) {
  return useQuery({
    queryKey: queryKeys.libraryLesson(bookId, unitKey, lessonKey),
    queryFn: ({ signal }) => getLibraryLesson(bookId, unitKey, lessonKey, signal),
    enabled: options.enabled ?? true,
  })
}

/** The resolved "Học tiếp" Lesson for a Profile's Grade; `data.lesson` is null when
 * nothing is visible yet (honest empty state, not an error). */
export function useLibraryHome(profileId: string) {
  return useQuery({
    queryKey: queryKeys.libraryHome(profileId),
    queryFn: ({ signal }) => getLibraryHome(profileId, signal),
  })
}

/** Starts a Session (Story 2.4: `POST /sessions`) for a resolved `ProblemSetRef`, e.g. the
 * Lesson `useLibraryHome()` resolved, or (Story 2.10) a `{kind: "replay",
 * source_session_id}` ref for "Luyện lại bài sai" -- `mode` should then be passed as
 * `"replay"`. Callers navigate to the Session route on success. */
export function useStartSession() {
  return useMutation({
    mutationFn: ({
      profileId,
      ref,
      mode,
    }: {
      profileId: string
      ref: StartSessionRefIn
      mode?: 'practice' | 'replay'
    }) => startSession(profileId, ref, mode),
  })
}

/** One chunk ("Phần i/n") of a started Session's bundle: each Problem's child_view, its
 * crop/page/audio URLs, and honest `attempted` progress state. `profileId` must be the
 * Session's own owner (Story 2.4 review follow-up: the backend now 403s a mismatch, the
 * same ownership check `usePostEvent()` already needed). */
export function useSessionBundle(sessionId: string, profileId: string, chunk: number) {
  return useQuery({
    queryKey: queryKeys.sessionBundle(sessionId, profileId, chunk),
    queryFn: ({ signal }) => getSessionBundle(sessionId, profileId, chunk, signal),
    enabled: sessionId !== '' && profileId !== '',
  })
}

/** The true-end-of-Session summary (Story 2.10: `GET /sessions/{id}/summary`) --
 * first-try-correct count, wrong Problem ids (for "Luyện lại bài sai"), and the Streak.
 * Only meaningful once `session_completed` has been posted; `enabled` lets the caller
 * defer the fetch until that post has landed. */
export function useSessionSummary(sessionId: string, profileId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.sessionSummary(sessionId, profileId),
    queryFn: ({ signal }) => getSessionSummary(sessionId, profileId, signal),
    enabled: enabled && sessionId !== '' && profileId !== '',
    retry: false,
  })
}

/** Posts one or more progress events (Story 2.4: `POST /sessions/{id}/events`); each
 * event's own client-generated UUIDv7 id makes a resend idempotent. Invalidates that
 * Session's bundle so `attempted` reflects the new event on the next read.
 *
 * Story 2.11: routed through `postEventsOrQueue()` -- a genuine network failure (the
 * server unreachable, not a 4xx/5xx) queues `events` in the IndexedDB outbox instead of
 * rejecting with the original error, and rejects with `QueuedOfflineError` instead; the
 * caller (a Problem/Session screen) must treat that specially -- show the offline screen,
 * never compute a local verdict. */
export function usePostEvent(sessionId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ profileId, events }: { profileId: string; events: EventIn[] }) =>
      postEventsOrQueue(defaultOutboxStore(), sessionId, profileId, events),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['sessions', sessionId, 'bundle'] })
    },
  })
}

/** Polls `GET /build/runs/current` every 2s while a run is active; stops once it settles
 * (done/failed/cancelled/paused) or there is no run at all. */
export function useCurrentRun() {
  return useQuery({
    queryKey: queryKeys.currentRun,
    queryFn: ({ signal }) => getCurrentRun(signal),
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ACTIVE_RUN_STATUSES.has(status) ? 2000 : false
    },
  })
}
