import { Link, Navigate } from 'react-router'
import type { BadgeKey } from '../api/client'
import { errorMessage } from '../api/errors'
import { useProfileBadges, useProfiles } from '../api/queries'
import { phrase } from '../audio/phrases'
import { speak } from '../audio/speech'
import Badge from '../components/Badge/Badge'
import { getCurrentProfileId } from '../profile'

// Fixed display order -- matches `progress_badges`'s own CHECK constraint/enum order
// (`backend/hoctap/learning/badges.py`'s `BADGE_KEYS`).
const BADGE_ORDER: BadgeKey[] = ['week1', 'streak7', 'stars100']

/**
 * "Huy hiệu của em" (Story 3.2): all 3 fixed badges, in a row -- earned ones shown
 * normally, unearned ones greyed out with their own 🔊 explaining how to earn them
 * (this story's frozen Boundaries).
 */
export default function Badges() {
  const profiles = useProfiles()
  const profileId = getCurrentProfileId()
  const list = profiles.data ?? []
  const current = list.find((p) => p.id === profileId) ?? (list.length === 1 ? list[0] : undefined)
  const badges = useProfileBadges(current?.id ?? '')

  if (profiles.isPending) {
    return (
      <main className="home">
        <p>Đang tải…</p>
      </main>
    )
  }

  if (profiles.isError) {
    return (
      <main className="home">
        <h1>{phrase('your_badges')}</h1>
        <p role="alert" className="form-error">
          {errorMessage(profiles.error)}
        </p>
        <button type="button" onClick={() => void profiles.refetch()}>
          Thử lại
        </button>
      </main>
    )
  }

  if (list.length === 0) return <Navigate to="/setup" replace />
  if (!current) return <Navigate to="/" replace />

  const byKey = new Map((badges.data ?? []).map((b) => [b.badge_key, b]))

  return (
    <main className="home">
      <h1>{phrase('your_badges')}</h1>

      {badges.isPending && <p>Đang tải…</p>}

      {badges.isError && (
        <>
          <p role="alert" className="form-error">
            {errorMessage(badges.error)}
          </p>
          <button type="button" onClick={() => void badges.refetch()}>
            Thử lại
          </button>
        </>
      )}

      {badges.data && (
        <div className="badges-grid" data-testid="badges-grid">
          {BADGE_ORDER.map((badgeKey) => (
            <Badge
              key={badgeKey}
              badgeKey={badgeKey}
              earned={byKey.get(badgeKey)?.earned ?? false}
              onSpeak={(text) => void speak(text)}
            />
          ))}
        </div>
      )}

      <p className="parent-link">
        <Link to="/">Về trang chủ</Link>
      </p>
    </main>
  )
}
