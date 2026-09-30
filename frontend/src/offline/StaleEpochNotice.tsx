import { useSyncExternalStore } from 'react'
import { dismissStaleEpochNotice, staleEpochSnapshot, subscribeStaleEpoch } from './dbEpoch'

/** Shown after queued answers were discarded because the data was restored from a backup. */
export default function StaleEpochNotice() {
  const stale = useSyncExternalStore(subscribeStaleEpoch, staleEpochSnapshot)
  if (!stale) return null
  return (
    <div role="status" className="stale-epoch-notice">
      <p>
        Dữ liệu trên máy chủ vừa được khôi phục từ bản sao lưu, nên các bài làm chưa gửi từ trước
        đó đã bị bỏ đi.
      </p>
      <button type="button" onClick={dismissStaleEpochNotice}>
        Đã hiểu
      </button>
    </div>
  )
}
