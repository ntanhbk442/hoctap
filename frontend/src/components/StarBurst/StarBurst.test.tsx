import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useMotion } from '../../hooks/useMotion'
import StarBurst from './StarBurst'

vi.mock('../../hooks/useMotion')

const mockMotion = vi.mocked(useMotion)

describe('StarBurst', () => {
  it('shows the accessible "N ⭐" text', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(<StarBurst count={22} />)
    expect(screen.getByRole('status')).toHaveTextContent('22 ngôi sao')
  })

  it('plays the burst animation class on mount when justEarned', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(<StarBurst count={3} justEarned />)
    expect(screen.getByRole('status')).toHaveClass('star-burst-bursting')
  })

  it('skips the burst class under reduced motion, showing the static end-state', () => {
    mockMotion.mockReturnValue({ reduced: true })
    render(<StarBurst count={3} justEarned />)
    const el = screen.getByRole('status')
    expect(el).not.toHaveClass('star-burst-bursting')
    expect(el).toHaveTextContent('3 ngôi sao')
  })

  it('does not burst when justEarned is false', () => {
    mockMotion.mockReturnValue({ reduced: false })
    render(<StarBurst count={3} />)
    expect(screen.getByRole('status')).not.toHaveClass('star-burst-bursting')
  })
})
