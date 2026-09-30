import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Link, Navigate, useNavigate } from 'react-router'
import { parentLogout } from '../api/client'
import { authRedirect, errorMessage } from '../api/errors'
import { queryKeys, useParentSession } from '../api/queries'
import GateCard from './GateCard'

export default function ParentHome() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const session = useParentSession()

  const logout = useMutation({
    mutationFn: parentLogout,
    onSuccess: () => {
      queryClient.removeQueries({ queryKey: queryKeys.parentSession })
      navigate('/parent/login', { replace: true })
    },
  })

  if (session.isError) {
    const target = authRedirect(session.error)
    if (target) return <Navigate to={target} replace />
  }

  return (
    <main className="parent">
      <h1>Khu vực phụ huynh</h1>
      {session.isPending && <p>Đang kiểm tra…</p>}
      {session.isError && (
        <>
          <p role="alert" className="form-error">
            {errorMessage(session.error)}
          </p>
          <button type="button" onClick={() => void session.refetch()}>
            Thử lại
          </button>
        </>
      )}
      {session.isSuccess && (
        <>
          <nav>
            <ul>
              <li>
                <Link to="/parent/dashboard">Tiến độ của bé</Link>
              </li>
              <li>
                <Link to="/parent/assignments">Giao bài</Link>
              </li>
              <li>
                <Link to="/parent/settings">Cài đặt</Link>
              </li>
              <li>
                <Link to="/parent/review">Duyệt nội dung</Link>
              </li>
              <li>
                <Link to="/parent/extraction">Chạy thử (pilot)</Link>
              </li>
            </ul>
          </nav>
          <section aria-labelledby="gate-heading">
            <h2 id="gate-heading">Chạy thử &amp; đánh giá</h2>
            <GateCard />
          </section>
          {logout.isError && (
            <p role="alert" className="form-error">
              {errorMessage(logout.error)}
            </p>
          )}
          <button type="button" onClick={() => logout.mutate()} disabled={logout.isPending}>
            Đăng xuất
          </button>
        </>
      )}
    </main>
  )
}
