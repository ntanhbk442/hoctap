import { fireEvent, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConceptGuide from '../components/ConceptGuide/ConceptGuide'
import { setCurrentProfileId } from '../profile'
import { mockApi, renderAt } from '../test/render'

vi.mock('../audio/speech', () => ({
  speak: vi.fn(() => Promise.resolve()),
  speechKey: vi.fn((text: string) => Promise.resolve(text)),
}))

const GUIDE = {
  explanation: 'Số nào có nhiều chục hơn thì lớn hơn.',
  example: { question: 'So sánh 35 và 28', steps: ['3 chục lớn hơn 2 chục'], answer: '35 > 28' },
}
const DETAIL = { concept_id: 'g1.a', name_vi: 'So sánh số', grade: 1, problem_count: 4, guide: GUIDE }
const LIST = [
  { concept_id: 'g1.a', name_vi: 'So sánh số', grade: 1, problem_count: 4 },
  { concept_id: 'g1.b', name_vi: 'Cộng trừ', grade: 1, problem_count: 0 },
]

function show(ids: string[], onClose = vi.fn()) {
  renderAt('/x', <ConceptGuide conceptIds={ids} grade={1} profileId="p1" onClose={onClose} />)
  return onClose
}

beforeEach(() => setCurrentProfileId('p1'))
afterEach(() => vi.unstubAllGlobals())

describe('ConceptGuide', () => {
  it('shows explanation, example and a 🔊 per text field', async () => {
    mockApi({ 'GET /api/v1/library/concepts/g1.a': { status: 200, body: DETAIL } })
    show(['g1.a'])
    expect(await screen.findByText(GUIDE.explanation)).toBeInTheDocument()
    expect(screen.getByText('So sánh 35 và 28')).toBeInTheDocument()
    expect(screen.getByText('35 > 28')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /^(Số nào|So sánh 35|3 chục|35 >)/ })).toHaveLength(4)
    expect(screen.getByRole('button', { name: 'Luyện tập' })).toBeInTheDocument()
  })

  it('says there is no Guide but still offers Luyện tập', async () => {
    mockApi({
      'GET /api/v1/library/concepts/g1.a': { status: 200, body: { ...DETAIL, guide: null } },
    })
    show(['g1.a'])
    expect(await screen.findByText('Chưa có hướng dẫn cho khái niệm này')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Luyện tập' })).toBeInTheDocument()
  })

  it('hides Luyện tập when the Concept has no visible Problems', async () => {
    mockApi({
      'GET /api/v1/library/concepts/g1.a': {
        status: 200,
        body: { ...DETAIL, guide: null, problem_count: 0 },
      },
    })
    show(['g1.a'])
    await screen.findByText('Chưa có hướng dẫn cho khái niệm này')
    expect(screen.queryByRole('button', { name: 'Luyện tập' })).not.toBeInTheDocument()
  })

  it('shows chips for several Concepts, first selected, and switches', async () => {
    mockApi({
      'GET /api/v1/library/concepts': { status: 200, body: LIST },
      'GET /api/v1/library/concepts/g1.a': { status: 200, body: DETAIL },
      'GET /api/v1/library/concepts/g1.b': {
        status: 200,
        body: { ...LIST[1], guide: { ...GUIDE, explanation: 'Phép cộng.' } },
      },
    })
    show(['g1.a', 'g1.b'])
    const chipA = await screen.findByRole('tab', { name: 'So sánh số' })
    expect(chipA).toHaveAttribute('aria-selected', 'true')
    fireEvent.click(screen.getByRole('tab', { name: 'Cộng trừ' }))
    expect(await screen.findByText('Phép cộng.')).toBeInTheDocument()
  })

  it('starts a concept Session and navigates to it', async () => {
    const fetchMock = mockApi({
      'GET /api/v1/library/concepts/g1.a': { status: 200, body: DETAIL },
      'POST /api/v1/sessions': { status: 201, body: { id: 's9' } },
    })
    const { router } = renderAt(
      '/x',
      <ConceptGuide conceptIds={['g1.a']} grade={1} profileId="p1" onClose={vi.fn()} />,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Luyện tập' }))
    expect(await screen.findByText('session player screen')).toBeInTheDocument()
    expect(router.state.location.pathname).toBe('/sessions/s9')
    const post = fetchMock.mock.calls.find(([url]) => url === '/api/v1/sessions')
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({
      profile_id: 'p1',
      ref: { kind: 'concept', concept_id: 'g1.a' },
      mode: 'concept',
    })
  })

  it('says it cannot load when the fetch fails, and Đóng still works', async () => {
    mockApi({})
    const onClose = show(['g1.a'])
    expect(await screen.findByText(/Chưa tải được hướng dẫn/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Đóng' }))
    expect(onClose).toHaveBeenCalled()
  })
})
