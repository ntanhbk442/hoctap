import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import HintBubble from './HintBubble'

describe('HintBubble', () => {
  it('shows the hint text and a speaker button that calls onSpeak', () => {
    const onSpeak = vi.fn()
    render(
      <HintBubble
        text="Hai số ở dưới cộng lại bằng số ở trên"
        onSpeak={onSpeak}
      />,
    )
    expect(screen.getByText('Hai số ở dưới cộng lại bằng số ở trên')).toBeInTheDocument()
    const speaker = screen.getByRole('button')
    fireEvent.click(speaker)
    expect(onSpeak).toHaveBeenCalledOnce()
  })

  it('shows the speaker as playing when speaking is true', () => {
    render(<HintBubble text="Gợi ý" speaking />)
    expect(screen.getByRole('button')).toHaveClass('speaker-button-playing')
  })
})
