import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { authRedirect } from './api/errors'
import StaleEpochNotice from './offline/StaleEpochNotice.tsx'
import { useOutboxAutoFlush } from './offline/useOutboxAutoFlush.ts'
import Assignments from './pages/Assignments.tsx'
import Badges from './pages/Badges.tsx'
import Dashboard from './pages/Dashboard.tsx'
import ExamStart from './pages/ExamStart.tsx'
import ExtractionPage from './pages/ExtractionPage.tsx'
import Home from './pages/Home.tsx'
import LessonDetail from './pages/LessonDetail.tsx'
import Library from './pages/Library.tsx'
import ParentHome from './pages/ParentHome.tsx'
import ParentLogin from './pages/ParentLogin.tsx'
import ProblemPreview from './pages/ProblemPreview.tsx'
import ProblemEditor from './pages/review/ProblemEditor.tsx'
import ReviewPage from './pages/review/ReviewPage.tsx'
import SessionPlayer from './pages/SessionPlayer.tsx'
import Settings from './pages/Settings.tsx'
import Setup from './pages/Setup.tsx'
import PWABadge from './PWABadge.tsx'
import WorksheetPage from './print/WorksheetPage.tsx'

// Story 9.1: the new base font/background (`index.css`'s `.child-shell` rule) must land on
// every CHILD route and nowhere else -- Parent Area screens (`/parent/*`) stay visually
// unchanged. Rather than restructure this flat routes array into nested router layout
// routes (more machinery than this needs), each child route's element is wrapped in this
// one thin div here; Parent routes are left exactly as they were.
function ChildShell({ children }: { children: ReactNode }) {
  return <div className="child-shell">{children}</div>
}

const routes = [
  { path: '/', element: <ChildShell><Home /></ChildShell> },
  { path: '/setup', element: <ChildShell><Setup /></ChildShell> },
  { path: '/library', element: <ChildShell><Library /></ChildShell> },
  {
    path: '/library/:bookId/:unitKey/:lessonKey',
    element: <ChildShell><LessonDetail /></ChildShell>,
  },
  { path: '/exam/new', element: <ChildShell><ExamStart /></ChildShell> },
  { path: '/badges', element: <ChildShell><Badges /></ChildShell> },
  { path: '/sessions/:sessionId', element: <ChildShell><SessionPlayer /></ChildShell> },
  { path: '/parent/login', element: <ParentLogin /> },
  { path: '/parent', element: <ParentHome /> },
  { path: '/parent/dashboard', element: <Dashboard /> },
  { path: '/parent/assignments', element: <Assignments /> },
  { path: '/parent/settings', element: <Settings /> },
  { path: '/parent/review', element: <ReviewPage /> },
  { path: '/parent/review/problems/:problemId', element: <ProblemEditor /> },
  { path: '/parent/problems/:problemId', element: <ProblemPreview /> },
  { path: '/parent/print', element: <WorksheetPage /> },
  { path: '/parent/extraction', element: <ExtractionPage /> },
  // Unknown client routes fall back to Home until later stories add screens.
  { path: '*', element: <ChildShell><Home /></ChildShell> },
]

const router = createBrowserRouter(routes)

const queryClient = new QueryClient({
  // Any guarded query that finds the session expired (401) or setup missing (403)
  // sends the parent to the login or setup screen.
  queryCache: new QueryCache({
    onError: (error) => {
      const target = authRedirect(error)
      if (target && router.state.location.pathname !== target) {
        void router.navigate(target, { replace: true })
      }
    },
  }),
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

export default function App() {
  // Story 2.11 (AD-10): flushes the IndexedDB event outbox in the background on every
  // `online` event (and once on mount), independent of whichever screen queued an event.
  useOutboxAutoFlush()
  return (
    <QueryClientProvider client={queryClient}>
      <StaleEpochNotice />
      <RouterProvider router={router} />
      <PWABadge />
    </QueryClientProvider>
  )
}
