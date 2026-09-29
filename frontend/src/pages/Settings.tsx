import { useState, type FormEvent } from 'react'
import { Link, Navigate } from 'react-router'
import type { Avatar, Profile } from '../api/client'
import { authRedirect, errorMessage } from '../api/errors'
import {
  useChangePin,
  useCreateProfile,
  useDeleteProfile,
  useParentSession,
  useProfiles,
  useUpdateProfile,
} from '../api/queries'
import { AVATARS, GRADES, PIN_PATTERN } from './avatars'

const MAX_PROFILES = 4

interface Draft {
  name: string
  avatar: Avatar
  grade: number
}

function ProfileFields({
  draft,
  onChange,
  idPrefix,
}: {
  draft: Draft
  onChange: (next: Draft) => void
  idPrefix: string
}) {
  return (
    <>
      <label>
        Tên
        <input
          type="text"
          maxLength={40}
          autoComplete="off"
          value={draft.name}
          onChange={(e) => onChange({ ...draft, name: e.target.value })}
        />
      </label>
      <div role="radiogroup" aria-label="Ảnh đại diện" className="avatar-grid">
        {AVATARS.map((a) => (
          <label key={a.key} className="avatar-option">
            <input
              type="radio"
              name={`${idPrefix}-avatar`}
              value={a.key}
              checked={draft.avatar === a.key}
              onChange={() => onChange({ ...draft, avatar: a.key })}
            />
            <span aria-hidden="true">{a.emoji}</span> {a.label}
          </label>
        ))}
      </div>
      <label>
        Lớp
        <select value={draft.grade} onChange={(e) => onChange({ ...draft, grade: Number(e.target.value) })}>
          {GRADES.map((g) => (
            <option key={g} value={g}>
              Lớp {g}
            </option>
          ))}
        </select>
      </label>
    </>
  )
}

function emojiOf(avatar: Avatar): string {
  return AVATARS.find((a) => a.key === avatar)?.emoji ?? ''
}

function ProfileItem({ profile, canDelete }: { profile: Profile; canDelete: boolean }) {
  const update = useUpdateProfile()
  const remove = useDeleteProfile()
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [draft, setDraft] = useState<Draft>({
    name: profile.name,
    avatar: profile.avatar,
    grade: profile.grade,
  })
  const [error, setError] = useState<string | null>(null)

  function save(event: FormEvent) {
    event.preventDefault()
    if (!draft.name.trim()) {
      setError('Vui lòng nhập tên của con.')
      return
    }
    setError(null)
    update.mutate(
      { id: profile.id, body: { ...draft, name: draft.name.trim() } },
      { onSuccess: () => setEditing(false), onError: (e) => setError(errorMessage(e)) },
    )
  }

  function toggleAutoPlay(next: boolean) {
    setError(null)
    update.mutate({ id: profile.id, body: { auto_play: next } }, { onError: (e) => setError(errorMessage(e)) })
  }

  function confirmDelete() {
    setError(null)
    remove.mutate(profile.id, { onError: (e) => setError(errorMessage(e)) })
  }

  return (
    <li>
      <div className="settings-row">
        <strong>
          <span aria-hidden="true">{emojiOf(profile.avatar)}</span> {profile.name}
        </strong>
        <span>Lớp {profile.grade}</span>
      </div>

      <label className="settings-row">
        <input
          type="checkbox"
          checked={profile.auto_play}
          disabled={update.isPending}
          onChange={(e) => toggleAutoPlay(e.target.checked)}
        />
        Tự động đọc đề của {profile.name}
      </label>

      {editing ? (
        <form className="parent-form" onSubmit={save} noValidate>
          <ProfileFields draft={draft} onChange={setDraft} idPrefix={profile.id} />
          <div className="settings-row">
            <button type="submit" disabled={update.isPending}>
              Lưu
            </button>
            <button type="button" onClick={() => setEditing(false)}>
              Huỷ
            </button>
          </div>
        </form>
      ) : (
        <div className="settings-row">
          <button type="button" onClick={() => setEditing(true)} aria-label={`Sửa hồ sơ ${profile.name}`}>
            Sửa
          </button>
          {canDelete && !confirming && (
            <button type="button" onClick={() => setConfirming(true)} aria-label={`Xoá hồ sơ ${profile.name}`}>
              Xoá
            </button>
          )}
        </div>
      )}

      {confirming && (
        <div role="alertdialog" aria-label={`Xác nhận xoá ${profile.name}`}>
          <p>
            Xoá hồ sơ của {profile.name}? Toàn bộ tiến độ học của {profile.name} sẽ mất và không thể
            khôi phục.
          </p>
          <div className="settings-row">
            <button type="button" onClick={confirmDelete} disabled={remove.isPending}>
              Xoá hồ sơ và tiến độ
            </button>
            <button type="button" onClick={() => setConfirming(false)}>
              Giữ lại
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </li>
  )
}

function AddProfile() {
  const create = useCreateProfile()
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<Draft>({ name: '', avatar: 'cat', grade: 1 })
  const [error, setError] = useState<string | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!draft.name.trim()) {
      setError('Vui lòng nhập tên của con.')
      return
    }
    setError(null)
    create.mutate(
      { ...draft, name: draft.name.trim() },
      {
        onSuccess: () => {
          setOpen(false)
          setDraft({ name: '', avatar: 'cat', grade: 1 })
        },
        onError: (e) => setError(errorMessage(e)),
      },
    )
  }

  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)}>
        Thêm hồ sơ
      </button>
    )
  }
  return (
    <form className="parent-form" onSubmit={submit} noValidate aria-label="Thêm hồ sơ">
      <ProfileFields draft={draft} onChange={setDraft} idPrefix="new" />
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      <div className="settings-row">
        <button type="submit" disabled={create.isPending}>
          Thêm
        </button>
        <button type="button" onClick={() => setOpen(false)}>
          Huỷ
        </button>
      </div>
    </form>
  )
}

function PinForm() {
  const change = useChangePin()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  function submit(event: FormEvent) {
    event.preventDefault()
    setDone(false)
    if (!PIN_PATTERN.test(current) || !PIN_PATTERN.test(next)) {
      setError('Mã PIN gồm đúng 4 chữ số.')
      return
    }
    if (next !== confirm) {
      setError('Hai mã PIN không khớp')
      return
    }
    setError(null)
    change.mutate(
      { current_pin: current, new_pin: next, new_pin_confirm: confirm },
      {
        onSuccess: () => {
          setCurrent('')
          setNext('')
          setConfirm('')
          setDone(true)
        },
        onError: (e) => setError(errorMessage(e)),
      },
    )
  }

  const digits = (set: (v: string) => void) => (e: { target: { value: string } }) =>
    set(e.target.value.replace(/[^0-9]/g, ''))

  return (
    <form className="parent-form" onSubmit={submit} noValidate aria-label="Đổi mã PIN">
      <label>
        Mã PIN hiện tại
        <input type="password" inputMode="numeric" autoComplete="current-password" maxLength={4} value={current} onChange={digits(setCurrent)} />
      </label>
      <label>
        Mã PIN mới
        <input type="password" inputMode="numeric" autoComplete="new-password" maxLength={4} value={next} onChange={digits(setNext)} />
      </label>
      <label>
        Nhập lại mã PIN mới
        <input type="password" inputMode="numeric" autoComplete="new-password" maxLength={4} value={confirm} onChange={digits(setConfirm)} />
      </label>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {done && <p role="status">Đã đổi mã PIN.</p>}
      <button type="submit" disabled={change.isPending}>
        Đổi mã PIN
      </button>
    </form>
  )
}

/** Parent Area settings (Story 4.1): Child Profiles (max 4), per-child auto-play, PIN. */
export default function Settings() {
  const session = useParentSession()
  const profiles = useProfiles()

  if (session.isError) {
    const target = authRedirect(session.error)
    if (target) return <Navigate to={target} replace />
  }

  const list = profiles.data ?? []
  return (
    <main className="parent">
      <p>
        <Link to="/parent">← Khu vực phụ huynh</Link>
      </p>
      <h1>Cài đặt</h1>
      {session.isPending && <p>Đang kiểm tra…</p>}
      {session.isError && (
        <p role="alert" className="form-error">
          {errorMessage(session.error)}
        </p>
      )}
      {session.isSuccess && (
        <>
          <section className="settings-section" aria-labelledby="profiles-heading">
            <h2 id="profiles-heading">Hồ sơ của con</h2>
            {profiles.isPending && <p>Đang tải…</p>}
            {profiles.isError && (
              <p role="alert" className="form-error">
                {errorMessage(profiles.error)}
              </p>
            )}
            <ul className="settings-list">
              {list.map((p) => (
                <ProfileItem key={p.id} profile={p} canDelete={list.length > 1} />
              ))}
            </ul>
            {list.length < MAX_PROFILES ? (
              <AddProfile />
            ) : (
              <p>Đã đủ {MAX_PROFILES} hồ sơ.</p>
            )}
          </section>
          <section className="settings-section" aria-labelledby="pin-heading">
            <h2 id="pin-heading">Mã PIN</h2>
            <PinForm />
          </section>
        </>
      )}
    </main>
  )
}
