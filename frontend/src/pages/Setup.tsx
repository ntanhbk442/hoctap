import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { ApiError, completeSetup, type Avatar, type SetupRequest } from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useSetupStatus } from '../api/queries'
import { AVATARS, GRADES, PIN_PATTERN } from './avatars'

function validate(pin: string, pinConfirm: string, name: string, avatar: Avatar | null): string | null {
  if (!PIN_PATTERN.test(pin)) return 'Mã PIN gồm đúng 4 chữ số.'
  if (pin !== pinConfirm) return 'Hai mã PIN không khớp'
  if (!name.trim()) return 'Vui lòng nhập tên của con.'
  if (!avatar) return 'Vui lòng chọn một ảnh đại diện.'
  return null
}

export default function Setup() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const status = useSetupStatus()
  const [pin, setPin] = useState('')
  const [pinConfirm, setPinConfirm] = useState('')
  const [name, setName] = useState('')
  const [avatar, setAvatar] = useState<Avatar | null>(null)
  const [grade, setGrade] = useState(1)
  const [formError, setFormError] = useState<string | null>(null)

  const setup = useMutation({
    mutationFn: (body: SetupRequest) => completeSetup(body),
    onSuccess: async () => {
      queryClient.setQueryData(queryKeys.setupStatus, { setup_required: false })
      await queryClient.invalidateQueries({ queryKey: queryKeys.parentSession })
      navigate('/parent', { replace: true })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.code === 'SETUP_DONE') {
        navigate('/parent/login', { replace: true })
        return
      }
      setFormError(errorMessage(error))
    },
  })

  if (status.data && !status.data.setup_required && !setup.isPending && !setup.isSuccess) {
    return <Navigate to="/parent" replace />
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const problem = validate(pin, pinConfirm, name, avatar)
    setFormError(problem)
    if (problem || !avatar) return
    setup.mutate({
      pin,
      pin_confirm: pinConfirm,
      profile: { name: name.trim(), avatar, grade },
    })
  }

  return (
    <main className="parent">
      <h1>Thiết lập ban đầu</h1>
      <form className="parent-form" onSubmit={onSubmit} noValidate>
        <fieldset>
          <legend>Mã PIN phụ huynh</legend>
          <label>
            Mã PIN (4 chữ số)
            <input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              maxLength={4}
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/[^0-9]/g, ''))}
            />
          </label>
          <label>
            Nhập lại mã PIN
            <input
              type="password"
              inputMode="numeric"
              autoComplete="new-password"
              maxLength={4}
              value={pinConfirm}
              onChange={(e) => setPinConfirm(e.target.value.replace(/[^0-9]/g, ''))}
            />
          </label>
        </fieldset>

        <fieldset>
          <legend>Hồ sơ của con</legend>
          <label>
            Tên
            <input
              type="text"
              maxLength={40}
              autoComplete="off"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <div role="radiogroup" aria-label="Ảnh đại diện" className="avatar-grid">
            {AVATARS.map((a) => (
              <label key={a.key} className="avatar-option">
                <input
                  type="radio"
                  name="avatar"
                  value={a.key}
                  checked={avatar === a.key}
                  onChange={() => setAvatar(a.key)}
                />
                <span aria-hidden="true">{a.emoji}</span> {a.label}
              </label>
            ))}
          </div>
          <label>
            Lớp
            <select value={grade} onChange={(e) => setGrade(Number(e.target.value))}>
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  Lớp {g}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        {formError && (
          <p role="alert" className="form-error">
            {formError}
          </p>
        )}
        <button type="submit" disabled={setup.isPending}>
          {setup.isPending ? 'Đang lưu…' : 'Hoàn tất'}
        </button>
      </form>
    </main>
  )
}
