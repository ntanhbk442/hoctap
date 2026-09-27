import './PWABadge.css'

import { useRegisterSW } from 'virtual:pwa-register/react'

/** Shows a prompt when a new service worker is waiting, so the user can reload into it. */
function PWABadge() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW()

  return (
    <div className="PWABadge-container">
      {needRefresh && (
        <div className="PWABadge-toast" role="alert" aria-labelledby="pwa-toast-message">
          <div className="PWABadge-toast-message">
            <span id="pwa-toast-message">Có phiên bản mới. Bấm Tải lại để cập nhật.</span>
          </div>
          <div>
            <button className="PWABadge-toast-button" onClick={() => updateServiceWorker(true)}>
              Tải lại
            </button>
            <button className="PWABadge-toast-button" onClick={() => setNeedRefresh(false)}>
              Đóng
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default PWABadge
