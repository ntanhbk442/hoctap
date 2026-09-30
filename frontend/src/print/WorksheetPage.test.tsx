import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fireEvent, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ProblemDoc, WorksheetOut } from '../api/client'
import { mockApi, renderAt } from '../test/render'
import WorksheetPage from './WorksheetPage'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const fixture = (name: string) =>
  JSON.parse(
    readFileSync(join(process.cwd(), '..', 'backend', 'tests', 'fixtures', 'problemdocs', `${name}.json`), 'utf-8'),
  ) as ProblemDoc

function sheet(names: string[]): WorksheetOut {
  return {
    kind: 'lesson',
    title: 'Tuần 5 Tiết 2',
    subtitle: 'Toán 1',
    problems: names.map((n) => {
      const doc = fixture(n)
      return { problem_id: doc.problem_id, doc, crop_url: null, image_urls: {} }
    }),
  }
}

const QUERY = '?book_id=b&unit_key=u&lesson_key=l'
const SESSION = { 'GET /api/v1/parent/session': { status: 200, body: { authenticated: true } } }

describe('WorksheetPage', () => {
  it('shows problem pages without answers, then the answer page', async () => {
    mockApi({
      ...SESSION,
      'GET /api/v1/parent/worksheet': { status: 200, body: sheet(['number_input', 'match']) },
    })
    renderAt(`/parent/print${QUERY}`, <WorksheetPage />, '/parent/print')
    const problems = await screen.findAllByTestId('ws-problem')
    expect(problems).toHaveLength(2)
    const answers = screen.getByTestId('ws-answers')
    expect(answers).toHaveClass('ws-answers')
    // The answers follow the last problem in document order.
    expect(problems[1].compareDocumentPosition(answers) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // No Hint or Solution anywhere; the Answer Key only inside the answer page.
    const doc = fixture('number_input')
    const part = doc.parts[0]
    expect(document.body.textContent).not.toContain(part.hint)
    for (const p of problems) {
      expect(within(p).queryByText(/Đáp án/)).toBeNull()
    }
    expect(within(answers).getByText(/l1|2 \+ 3/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In phiếu' })).toBeEnabled()
  })

  it('prints through the browser', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    mockApi({
      ...SESSION,
      'GET /api/v1/parent/worksheet': { status: 200, body: sheet(['number_input']) },
    })
    renderAt(`/parent/print${QUERY}`, <WorksheetPage />, '/parent/print')
    await screen.findAllByTestId('ws-problem')
    fireEvent.click(screen.getByRole('button', { name: 'In phiếu' }))
    expect(print).toHaveBeenCalled()
  })

  it('says the set is empty and disables printing', async () => {
    mockApi({
      ...SESSION,
      'GET /api/v1/parent/worksheet': { status: 200, body: sheet([]) },
    })
    renderAt(`/parent/print${QUERY}`, <WorksheetPage />, '/parent/print')
    expect(await screen.findByText('Phiếu này chưa có bài nào để in.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'In phiếu' })).toBeDisabled()
    expect(screen.queryByTestId('ws-answers')).toBeNull()
  })

  it('redirects to the login screen without the parent cookie', async () => {
    mockApi({
      'GET /api/v1/parent/worksheet': {
        status: 401,
        body: { error: { code: 'UNAUTHORIZED', message: 'Cần nhập mã PIN.' } },
      },
    })
    renderAt(`/parent/print${QUERY}`, <WorksheetPage />, '/parent/print')
    expect(await screen.findByText('login screen')).toBeInTheDocument()
  })

  it('shows the error for an unknown profile', async () => {
    mockApi({
      'GET /api/v1/parent/worksheet': {
        status: 404,
        body: { error: { code: 'PROFILE_NOT_FOUND', message: 'Không tìm thấy hồ sơ.' } },
      },
    })
    renderAt('/parent/print?concept_id=g1.x&profile_id=nope', <WorksheetPage />, '/parent/print')
    expect(await screen.findByRole('alert')).toHaveTextContent('Không tìm thấy hồ sơ.')
    expect(screen.getByRole('button', { name: 'In phiếu' })).toBeDisabled()
  })

  it('asks for a set when the link has none', () => {
    mockApi({})
    renderAt('/parent/print', <WorksheetPage />, '/parent/print')
    expect(screen.getByRole('alert')).toHaveTextContent('Chưa chọn')
  })
})
