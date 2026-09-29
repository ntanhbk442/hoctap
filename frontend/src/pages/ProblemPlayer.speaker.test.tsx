import { fireEvent, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BundleProblemOut } from '../api/client'
import { stop as stopAudio } from '../audio/player'
import { setCurrentProfileId } from '../profile'
import { mockApi, renderAt } from '../test/render'
import ProblemPlayer from './ProblemPlayer'

// Story 2.9 review finding #1: `ProblemPlayer.test.tsx` mocks `../audio/player` wholesale for
// its other tests, so it can never prove the instruction's `SpeakerButton` is wired to the
// REAL shared player -- only that a mocked `isAudioUnlocked`/`stop` get called. This file
// keeps the real `audio/player.ts` module (only `isAudioUnlocked` is overridden, to keep the
// auto-play-on-open effect from also firing and racing this test's own manual tap), so
// `playKey()`/`subscribe()`/the real `<audio>` element singleton are all exercised exactly as
// they would be in the running app.
vi.mock('../audio/player', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../audio/player')>()
  return { ...actual, isAudioUnlocked: () => false }
})

const PROFILE_ID = 'profile-1'
const SESSION_ID = 'session-1'
const ROUTE = '/sessions/session-1'
const PATTERN = '/sessions/:sessionId'
const INSTRUCTION = 'Tính:'

function bundleProblem(): BundleProblemOut {
  return {
    problem: {
      schema_version: 'v1',
      problem_id: 'toan1-2020-q1.tuan-5.tiet-2.bai-1',
      book_id: 'toan1-2020-q1',
      unit_key: 'tuan-5',
      lesson_key: 'tiet-2',
      problem_label: 'bai-1',
      display_label: 'Bài 1',
      instruction: INSTRUCTION,
      layout: 'sequence',
      source_pages: [{ page: 12, bbox: [0, 0, 1, 1] }],
      images: [],
      concept_ids: [],
      concept_proposals: [],
      parts: [
        {
          part_key: 'a',
          type: 'number_input',
          prompt: '',
          image_keys: [],
          template: '3 + 2 = [[s1]]',
          slots: [{ slot_key: 's1' }],
        },
      ],
    } as unknown as BundleProblemOut['problem'],
    crop_urls: ['/assets-data/crops/toan1-2020-q1/x/_problem.jpg'],
    page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
    audio: {},
    attempted: false,
  }
}

beforeEach(() => {
  setCurrentProfileId(PROFILE_ID)
})

afterEach(() => {
  stopAudio()
})

describe('ProblemPlayer instruction SpeakerButton (finding #1: real player wiring)', () => {
  it('renders next to the instruction; a tap plays it through the real shared player and `playing` reflects that state', async () => {
    mockApi({})
    renderAt(
      ROUTE,
      <ProblemPlayer
        sessionId={SESSION_ID}
        profileId={PROFILE_ID}
        bundleProblem={bundleProblem()}
        stars={0}
        onStarEarned={vi.fn()}
        onDone={vi.fn()}
      />,
      PATTERN,
    )

    expect(screen.getByText(INSTRUCTION)).toBeInTheDocument()
    const button = screen.getByRole('button', { name: INSTRUCTION })
    expect(button).toBeInTheDocument()
    expect(button).not.toHaveClass('speaker-button-playing')

    fireEvent.click(button)

    // The real `player.ts`'s `playKey()` (via `speech.ts`'s `speak()`) sets the shared
    // player's state to `playing` for this instruction's real `speechKey()` -- `InstructionLine`
    // subscribes to that and re-renders, so the SAME button (not a mock) reflects it.
    await waitFor(() => expect(button).toHaveClass('speaker-button-playing'))
  })
})
