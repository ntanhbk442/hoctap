import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ChildTopBar from './ChildTopBar'

describe('ChildTopBar', () => {
  it('always renders a focusable, labelled back button that calls onBack on tap', () => {
    const onBack = vi.fn()
    render(<ChildTopBar onBack={onBack} />)
    const back = screen.getByRole('button', { name: 'Quay lại' })
    fireEvent.click(back)
    expect(onBack).toHaveBeenCalledOnce()
  })

  it('renders nothing extra when dots and onSpeak are both omitted', () => {
    render(<ChildTopBar onBack={() => {}} />)
    expect(screen.queryByRole('list', { name: 'Tiến độ' })).not.toBeInTheDocument()
    // Only the back button -- no 🔊.
    expect(screen.getAllByRole('button')).toHaveLength(1)
  })

  it('renders the right progress-dot states when dots are passed', () => {
    render(<ChildTopBar onBack={() => {}} dots={['done', 'current', 'todo']} />)
    const dots = screen.getByRole('list', { name: 'Tiến độ' })
    expect(dots).toBeInTheDocument()
    expect(dots.querySelectorAll('.progress-dot-done')).toHaveLength(1)
    expect(dots.querySelectorAll('.progress-dot-current')).toHaveLength(1)
    expect(dots.querySelectorAll('.progress-dot-todo')).toHaveLength(1)
  })

  it('renders no dots list when dots is an empty array', () => {
    render(<ChildTopBar onBack={() => {}} dots={[]} />)
    expect(screen.queryByRole('list', { name: 'Tiến độ' })).not.toBeInTheDocument()
  })

  it('renders a 🔊 that fires onSpeak when provided', () => {
    const onSpeak = vi.fn()
    render(<ChildTopBar onBack={() => {}} onSpeak={onSpeak} />)
    fireEvent.click(screen.getByRole('button', { name: 'Nghe lại' }))
    expect(onSpeak).toHaveBeenCalledOnce()
  })
})
