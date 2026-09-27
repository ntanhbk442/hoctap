import { fireEvent, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi, renderAt } from '../test/render'
import ParentLogin from './ParentLogin'

afterEach(() => {
  vi.unstubAllGlobals()
})

const SIGNED_OUT = {
  'GET /api/v1/parent/session': {
    status: 401,
    body: { error: { code: 'UNAUTHORIZED', message: 'Cần nhập mã PIN.' } },
  },
}

function submit(pin: string) {
  fireEvent.change(screen.getByLabelText('Mã PIN'), { target: { value: pin } })
  fireEvent.click(screen.getByRole('button', { name: 'Vào' }))
}

describe('ParentLogin', () => {
  it('shows the Vietnamese message for a wrong PIN', async () => {
    mockApi({
      ...SIGNED_OUT,
      'POST /api/v1/parent/login': {
        status: 401,
        body: { error: { code: 'PIN_INCORRECT', message: 'Mã PIN chưa đúng' } },
      },
    })
    renderAt('/parent/login', <ParentLogin />)
    submit('9999')
    expect(await screen.findByRole('alert')).toHaveTextContent('Mã PIN chưa đúng')
  })

  it('shows the lockout message', async () => {
    const message = 'Nhập sai mã PIN quá nhiều lần. Vui lòng thử lại sau 5 phút.'
    mockApi({
      ...SIGNED_OUT,
      'POST /api/v1/parent/login': {
        status: 429,
        body: { error: { code: 'PIN_LOCKED', message } },
      },
    })
    renderAt('/parent/login', <ParentLogin />)
    submit('1234')
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
  })

  it('goes to the Parent Area after a correct PIN', async () => {
    mockApi({ ...SIGNED_OUT, 'POST /api/v1/parent/login': { status: 204 } })
    renderAt('/parent/login', <ParentLogin />)
    submit('1234')
    expect(await screen.findByText('parent screen')).toBeInTheDocument()
  })

  it('goes to setup on 403 SETUP_REQUIRED from login', async () => {
    mockApi({
      ...SIGNED_OUT,
      'POST /api/v1/parent/login': {
        status: 403,
        body: { error: { code: 'SETUP_REQUIRED', message: 'Cần thiết lập mã PIN trước.' } },
      },
    })
    renderAt('/parent/login', <ParentLogin />)
    submit('1234')
    expect(await screen.findByText('setup screen')).toBeInTheDocument()
  })

  it('skips the PIN prompt when already signed in', async () => {
    mockApi({ 'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } } })
    renderAt('/parent/login', <ParentLogin />)
    expect(await screen.findByText('parent screen')).toBeInTheDocument()
  })
})
