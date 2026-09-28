import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ChoiceChip from './ChoiceChip'

describe('ChoiceChip', () => {
  it('shows a text child and calls onClick', () => {
    const onClick = vi.fn()
    render(<ChoiceChip onClick={onClick}>&lt;</ChoiceChip>)
    fireEvent.click(screen.getByRole('button', { name: '<' }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('shows an image child', () => {
    render(
      <ChoiceChip ariaLabel="quả táo">
        <img src="apple.png" alt="" />
      </ChoiceChip>,
    )
    expect(screen.getByRole('button', { name: 'quả táo' })).toBeInTheDocument()
  })

  it('applies the selected class and aria-pressed', () => {
    const { rerender } = render(<ChoiceChip>=</ChoiceChip>)
    const button = screen.getByRole('button')
    expect(button).not.toHaveClass('choice-chip-selected')
    expect(button).toHaveAttribute('aria-pressed', 'false')
    rerender(<ChoiceChip selected>=</ChoiceChip>)
    expect(screen.getByRole('button')).toHaveClass('choice-chip-selected')
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
  })

  it('renders at least 64px touch-min', () => {
    render(<ChoiceChip>&gt;</ChoiceChip>)
    const button = screen.getByRole('button')
    expect(Number.parseInt(button.style.minWidth, 10)).toBeGreaterThanOrEqual(64)
    expect(Number.parseInt(button.style.minHeight, 10)).toBeGreaterThanOrEqual(64)
  })
})
