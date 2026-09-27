import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'
import { parentLogin } from '../api/client'
import { authRedirect, errorMessage } from '../api/errors'
import { queryKeys, useParentSession } from '../api/queries'
import { PIN_PATTERN } from './avatars'

export default function ParentLogin() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [pin, setPin] = useState('')
  const [error, setError] = useState<string | null>(null)
  const session = useParentSession()

  const login = useMutation({
    mutationFn: (value: string) => parentLogin({ pin: value }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.parentSession })
      navigate('/parent', { replace: true })
    },
    onError: (err) => {
      if (authRedirect(err) === '/setup') {
        navigate('/setup', { replace: true })
        return
      }
      setError(errorMessage(err))
      setPin('')
    },
  })

  // Already signed in: skip the PIN prompt. Before setup, go to the setup screen.
  if (session.isSuccess) return <Navigate to="/parent" replace />
  if (session.isError && authRedirect(session.error) === '/setup') {
    return <Navigate to="/setup" replace />
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!PIN_PATTERN.test(pin)) {
      setError('Mã PIN gồm đúng 4 chữ số.')
      return
    }
    setError(null)
    login.mutate(pin)
  }

  return (
    <main className="parent">
      <h1>Khu vực phụ huynh</h1>
      <form className="parent-form" onSubmit={onSubmit} noValidate>
        <label>
          Mã PIN
          <input
            type="password"
            inputMode="numeric"
            autoComplete="current-password"
            maxLength={4}
            autoFocus
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/[^0-9]/g, ''))}
          />
        </label>
        {error && (
          <p role="alert" className="form-error">
            {error}
          </p>
        )}
        <button type="submit" disabled={login.isPending}>
          Vào
        </button>
      </form>
    </main>
  )
}
