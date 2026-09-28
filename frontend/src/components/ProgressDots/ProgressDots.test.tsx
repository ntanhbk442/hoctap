import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import ProgressDots from './ProgressDots'

describe('ProgressDots', () => {
  it('renders one dot per entry, with the matching class in order', () => {
    render(<ProgressDots dots={['done', 'current', 'todo', 'todo']} />)
    const dots = screen.getAllByRole('listitem')
    expect(dots).toHaveLength(4)
    expect(dots[0]).toHaveClass('progress-dot-done')
    expect(dots[1]).toHaveClass('progress-dot-current')
    expect(dots[2]).toHaveClass('progress-dot-todo')
    expect(dots[3]).toHaveClass('progress-dot-todo')
  })
})
