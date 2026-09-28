import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  getCatalogueBooks,
  getConcepts,
  getCurrentRun,
  getGate,
  getHealth,
  getParentSession,
  getReviewBooks,
  getReviewProblem,
  getReviewProblems,
  getReviewQueue,
  getSetupStatus,
  getSpotCheck,
  type ProblemFilter,
} from './client'

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
