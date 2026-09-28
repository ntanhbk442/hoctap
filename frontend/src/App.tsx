import { QueryCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, RouterProvider } from 'react-router'
import { authRedirect } from './api/errors'
import ExtractionPage from './pages/ExtractionPage.tsx'
import Home from './pages/Home.tsx'
import LessonDetail from './pages/LessonDetail.tsx'
import Library from './pages/Library.tsx'
import ParentHome from './pages/ParentHome.tsx'
import ParentLogin from './pages/ParentLogin.tsx'
import ProblemEditor from './pages/review/ProblemEditor.tsx'
import ReviewPage from './pages/review/ReviewPage.tsx'
import SessionPlayer from './pages/SessionPlayer.tsx'
import Setup from './pages/Setup.tsx'
import PWABadge from './PWABadge.tsx'

const routes = [
  { path: '/', element: <Home /> },
  { path: '/setup', element: <Setup /> },
  { path: '/library', element: <Library /> },
  { path: '/library/:bookId/:unitKey/:lessonKey', element: <LessonDetail /> },
  { path: '/sessions/:sessionId', element: <SessionPlayer /> },
  { path: '/parent/login', element: <ParentLogin /> },
  { path: '/parent', element: <ParentHome /> },
  { path: '/parent/review', element: <ReviewPage /> },
  { path: '/parent/review/problems/:problemId', element: <ProblemEditor /> },
  { path: '/parent/extraction', element: <ExtractionPage /> },
  // Unknown client routes fall back to Home until later stories add screens.
  { path: '*', element: <Home /> },
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
  return (
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <PWABadge />
    </QueryClientProvider>
  )
}
