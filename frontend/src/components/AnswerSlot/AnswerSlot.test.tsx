import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useMotion } from '../../hooks/useMotion'
import AnswerSlot from './AnswerSlot'

vi.mock('../../hooks/useMotion')

const mockMotion = vi.mocked(useMotion)

describe('AnswerSlot', () => {
  it('renders at least 80px (key size), which is above touch-min', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(<AnswerSlot state="default" label="Ô số 1" />)
    const el = screen.getByRole('button')
    expect(el.style.width).toBe('80px')
    expect(el.style.height).toBe('80px')
  })

  it.each([
    ['default', 'answer-slot-default'],
    ['active', 'answer-slot-active'],
    ['correct', 'answer-slot-correct'],
    ['wrong', 'answer-slot-wrong'],
  ] as const)('applies the %s state class', (state, className) => {
    mockMotion.mockReturnValue({ reduced: false })
    render(<AnswerSlot state={state} label="Ô số 1" />)
    expect(screen.getByRole('button')).toHaveClass(className)
  })

  it('shakes when wrong, unless reduced motion is on', () => {
    mockMotion.mockReturnValue({ reduced: false })
    const { rerender } = render(<AnswerSlot state="wrong" label="Ô số 1" />)
    expect(screen.getByRole('button')).toHaveClass('answer-slot-shake')

    mockMotion.mockReturnValue({ reduced: true })
    rerender(<AnswerSlot state="wrong" label="Ô số 1" />)
    expect(screen.getByRole('button')).not.toHaveClass('answer-slot-shake')
    // The colour/icon change still shows even with the shake skipped.
    expect(screen.getByRole('button')).toHaveClass('answer-slot-wrong')
  })

  it('includes the current value in the accessible name, updated as it changes', () => {
    mockMotion.mockReturnValue({ reduced: false })
    const { rerender } = render(<AnswerSlot state="active" label="Ô số 1" />)
    expect(screen.getByRole('button', { name: 'Ô số 1: trống' })).toBeInTheDocument()
    rerender(<AnswerSlot state="active" label="Ô số 1" value="4" />)
    expect(screen.getByRole('button', { name: 'Ô số 1: 4' })).toBeInTheDocument()
  })

  it('announces the correct/wrong state text for screen readers', () => {
    mockMotion.mockReturnValue({ reduced: false })
    const { rerender } = render(<AnswerSlot state="correct" label="Ô số 1" />)
    expect(screen.getByRole('status')).toHaveTextContent('Đúng rồi!')
    rerender(<AnswerSlot state="wrong" label="Ô số 1" />)
    expect(screen.getByRole('status')).toHaveTextContent('Chưa đúng, em thử lại nhé!')
  })
})
