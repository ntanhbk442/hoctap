import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SpeakerButton from './SpeakerButton'

describe('SpeakerButton', () => {
  it('has an accessible name and calls onClick', () => {
    const onClick = vi.fn()
    render(<SpeakerButton label="Nghe lại câu hỏi" onClick={onClick} />)
    const button = screen.getByRole('button', { name: 'Nghe lại câu hỏi' })
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('renders at least touch-min (64px)', () => {
    render(<SpeakerButton label="Nghe lại" />)
    const button = screen.getByRole('button')
    expect(button.style.width).toBe('64px')
    expect(button.style.height).toBe('64px')
  })

  it('shows the pulsing class only while playing', () => {
    const { rerender } = render(<SpeakerButton label="Nghe lại" playing />)
    expect(screen.getByRole('button')).toHaveClass('speaker-button-playing')
    rerender(<SpeakerButton label="Nghe lại" playing={false} />)
    expect(screen.getByRole('button')).not.toHaveClass('speaker-button-playing')
  })
})
