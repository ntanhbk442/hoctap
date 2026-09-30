import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { mockApi } from '../test/render'
import FlagButton from '../components/FlagButton/FlagButton'

afterEach(() => {
  vi.unstubAllGlobals()
})

const URL = '/api/v1/problems/pr/flag'

describe('FlagButton', () => {
  it('confirms with Có, posts the profile id and shows the calm message', async () => {
    const fetchMock = mockApi({ [`POST ${URL}`]: { status: 200, body: { ok: true } } })
    render(<FlagButton problemId="pr" profileId="p1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Báo cho bố mẹ' }))
    fireEvent.click(screen.getByRole('button', { name: 'Có' }))
    expect(await screen.findByText('Đã báo cho bố mẹ')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === 'POST')
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ profile_id: 'p1' })
  })

  it('stores nothing on Không', () => {
    const fetchMock = mockApi({})
    render(<FlagButton problemId="pr" profileId="p1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Báo cho bố mẹ' }))
    fireEvent.click(screen.getByRole('button', { name: 'Không' }))
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: 'Báo cho bố mẹ' })).toBeInTheDocument()
  })

  it('shows a neutral retry message when the call fails', async () => {
    mockApi({ [`POST ${URL}`]: { status: 502 } })
    render(<FlagButton problemId="pr" profileId="p1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Báo cho bố mẹ' }))
    fireEvent.click(screen.getByRole('button', { name: 'Có' }))
    expect(await screen.findByText('Chưa gửi được, thử lại nhé')).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: 'Báo cho bố mẹ' })).toBeInTheDocument(),
    )
    expect(document.body.textContent).not.toMatch(/Sai!|✗/)
  })
})
