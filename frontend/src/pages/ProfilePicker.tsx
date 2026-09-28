import type { Profile } from '../api/client'
import { AVATARS } from './avatars'

export interface ProfilePickerProps {
  profiles: Profile[]
  onSelect: (id: string) => void
}

function emoji(avatar: Profile['avatar']): string {
  return AVATARS.find((a) => a.key === avatar)?.emoji ?? '👤'
}

/**
 * Shown on Home when there is more than one Child Profile (Story 2.3). No PIN, no parent
 * gate -- Child Profile selection is deliberately open (`api/profiles.py`'s docstring: "the
 * child picks one without a PIN"). Reuses `pages/avatars.ts`'s existing avatar-icon mapping
 * (already used by Setup/the Parent Area).
 */
export default function ProfilePicker({ profiles, onSelect }: ProfilePickerProps) {
  return (
    <main className="home">
      <h1>Ai đang học vậy?</h1>
      <div className="profile-picker-grid">
        {profiles.map((p) => (
          <button
            key={p.id}
            type="button"
            className="profile-picker-card"
            onClick={() => onSelect(p.id)}
          >
            <span className="profile-picker-avatar" aria-hidden="true">
              {emoji(p.avatar)}
            </span>
            <span className="profile-picker-name">{p.name}</span>
          </button>
        ))}
      </div>
    </main>
  )
}
