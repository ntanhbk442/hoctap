import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import HomeCard from './HomeCard'

afterEach(() => {
  vi.useRealTimers()
})

describe('HomeCard', () => {
  it('shows its title and calls onClick on a tap', () => {
    const onClick = vi.fn()
    render(<HomeCard title="Bài hôm nay" onClick={onClick} />)
    fireEvent.click(screen.getByRole('button', { name: /Bài hôm nay/ }))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('applies the wide variant class for "Bài hôm nay"', () => {
    render(<HomeCard title="Bài hôm nay" wide />)
    expect(screen.getByRole('button')).toHaveClass('home-card-wide')
  })

  it('plays the label via long-press instead of opening the card', () => {
    vi.useFakeTimers()
    const onClick = vi.fn()
    const onLongPress = vi.fn()
    render(<HomeCard title="Luyện lại" onClick={onClick} onLongPress={onLongPress} />)
    const card = screen.getByRole('button')
    fireEvent.pointerDown(card)
    vi.advanceTimersByTime(600)
    fireEvent.pointerUp(card)
    fireEvent.click(card) // browsers still fire a click after a long-press pointerup
    expect(onLongPress).toHaveBeenCalledOnce()
    expect(onClick).not.toHaveBeenCalled()
  })

  it('does not permanently swallow keyboard activation after a prior long-press', () => {
    vi.useFakeTimers()
    const onClick = vi.fn()
    const onLongPress = vi.fn()
    render(<HomeCard title="Luyện lại" onClick={onClick} onLongPress={onLongPress} />)
    const card = screen.getByRole('button')

    // A long-press via pointer first (suppresses that click, as above).
    fireEvent.pointerDown(card)
    vi.advanceTimersByTime(600)
    fireEvent.pointerUp(card)
    fireEvent.click(card)
    expect(onLongPress).toHaveBeenCalledOnce()
    expect(onClick).not.toHaveBeenCalled()

    // A later keyboard activation (no pointer events at all) must still open the card.
    fireEvent.keyDown(card, { key: 'Enter' })
    fireEvent.click(card)
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('clears a pending long-press timer on pointer cancel (scroll/gesture interruption)', () => {
    vi.useFakeTimers()
    const onLongPress = vi.fn()
    render(<HomeCard title="Luyện lại" onLongPress={onLongPress} />)
    const card = screen.getByRole('button')
    fireEvent.pointerDown(card)
    fireEvent.pointerCancel(card)
    vi.advanceTimersByTime(600)
    expect(onLongPress).not.toHaveBeenCalled()
  })

  it('clears an earlier pending timer if pointerdown fires again before it completes', () => {
    vi.useFakeTimers()
    const onLongPress = vi.fn()
    render(<HomeCard title="Luyện lại" onLongPress={onLongPress} />)
    const card = screen.getByRole('button')
    fireEvent.pointerDown(card)
    vi.advanceTimersByTime(300)
    fireEvent.pointerDown(card) // a second pointerdown before the first timer fires
    vi.advanceTimersByTime(300)
    // Only 300ms have elapsed since the second pointerdown — the (would-be) first timer's
    // total of 600ms has passed, but it must have been cleared, not fired twice or early.
    expect(onLongPress).not.toHaveBeenCalled()
    vi.advanceTimersByTime(300)
    expect(onLongPress).toHaveBeenCalledOnce()
  })
})
