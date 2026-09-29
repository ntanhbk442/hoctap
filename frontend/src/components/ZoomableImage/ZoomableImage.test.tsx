import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ZoomableImage from './ZoomableImage'

// jsdom doesn't implement pointer capture at all -- stub it as a no-op so
// `handlePointerDown`'s `event.currentTarget.setPointerCapture(...)` doesn't throw.
beforeEach(() => {
  Element.prototype.setPointerCapture = vi.fn()
})

function pinchZoomIn(container: HTMLElement) {
  const viewer = container.querySelector('.zoomable-image') as HTMLElement
  fireEvent.pointerDown(viewer, { pointerId: 1, clientX: 100, clientY: 100 })
  fireEvent.pointerDown(viewer, { pointerId: 2, clientX: 200, clientY: 100 })
  // Pinch outward: inter-pointer distance grows from 100 to 300 (scale delta 3x).
  fireEvent.pointerMove(viewer, { pointerId: 2, clientX: 400, clientY: 100 })
  fireEvent.pointerUp(viewer, { pointerId: 1, clientX: 100, clientY: 100 })
  fireEvent.pointerUp(viewer, { pointerId: 2, clientX: 400, clientY: 100 })
}

describe('ZoomableImage', () => {
  it('does not show the reset button at the default scale', () => {
    render(<ZoomableImage src="/crop.png" alt="Trang bài tập" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('shows the reset button once pinch-zoomed past scale 1', () => {
    const { container } = render(<ZoomableImage src="/crop.png" alt="Trang bài tập" />)
    pinchZoomIn(container)
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('resets to scale 1 (reset button disappears) on a double-tap within 300ms', () => {
    vi.useFakeTimers()
    const { container } = render(<ZoomableImage src="/crop.png" alt="Trang bài tập" />)
    pinchZoomIn(container)
    expect(screen.getByRole('button')).toBeInTheDocument()
    // The pinch's own initial single-pointer-down already set `lastTapAt` -- clear that
    // window first so only the two deliberate taps below are what's under test.
    vi.advanceTimersByTime(1000)

    const viewer = container.querySelector('.zoomable-image') as HTMLElement
    fireEvent.pointerDown(viewer, { pointerId: 3, clientX: 150, clientY: 150 })
    fireEvent.pointerUp(viewer, { pointerId: 3, clientX: 150, clientY: 150 })
    vi.advanceTimersByTime(100) // well within the 300ms double-tap window
    fireEvent.pointerDown(viewer, { pointerId: 4, clientX: 150, clientY: 150 })

    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    vi.useRealTimers()
  })

  it('does NOT reset on two single-taps more than 300ms apart', () => {
    vi.useFakeTimers()
    const { container } = render(<ZoomableImage src="/crop.png" alt="Trang bài tập" />)
    pinchZoomIn(container)
    expect(screen.getByRole('button')).toBeInTheDocument()
    // Same as above: clear the pinch's own dangling `lastTapAt` window first.
    vi.advanceTimersByTime(1000)

    const viewer = container.querySelector('.zoomable-image') as HTMLElement
    fireEvent.pointerDown(viewer, { pointerId: 3, clientX: 150, clientY: 150 })
    fireEvent.pointerUp(viewer, { pointerId: 3, clientX: 150, clientY: 150 })
    vi.advanceTimersByTime(400) // past the 300ms double-tap window
    fireEvent.pointerDown(viewer, { pointerId: 4, clientX: 150, clientY: 150 })

    expect(screen.getByRole('button')).toBeInTheDocument()
    vi.useRealTimers()
  })
})
