import { Link, Navigate } from 'react-router'
import { errorMessage } from '../api/errors'
import { useHealth, useSetupStatus } from '../api/queries'

export default function Home() {
  const health = useHealth()
  const setup = useSetupStatus()

  if (setup.data?.setup_required) return <Navigate to="/setup" replace />

  if (setup.isPending) {
    return (
      <main className="home">
        <p>Đang tải…</p>
      </main>
    )
  }

  if (setup.isError) {
    return (
      <main className="home">
        <h1>Học Tập</h1>
        <p role="alert" className="form-error">
          {errorMessage(setup.error)}
        </p>
        <button type="button" onClick={() => void setup.refetch()}>
          Thử lại
        </button>
      </main>
    )
  }

  let status: string
  if (health.isPending) status = 'đang kiểm tra…'
  else if (health.isError) status = 'không kết nối được máy chủ'
  else status = health.data.status

  return (
    <main className="home">
      <h1>Học Tập</h1>
      <p>
        Máy chủ: <strong data-testid="health-status">{status}</strong>
        {health.data && <span className="version"> (v{health.data.version})</span>}
      </p>
      <p className="parent-link">
        <Link to="/parent/login">Khu vực phụ huynh</Link>
      </p>
    </main>
  )
}
