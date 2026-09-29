import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Profile } from '../api/client'
import ProfilePicker from './ProfilePicker'

const PROFILES: Profile[] = [
  { id: 'a', name: 'Bin', avatar: 'cat', grade: 1, auto_play: true },
  { id: 'b', name: 'An', avatar: 'dog', grade: 2, auto_play: true },
]

describe('ProfilePicker', () => {
  it('shows one card per profile, with its avatar icon and name', () => {
    render(<ProfilePicker profiles={PROFILES} onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: /Bin/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /An/ })).toBeInTheDocument()
  })

  it('calls onSelect with the tapped profile id', () => {
    const onSelect = vi.fn()
    render(<ProfilePicker profiles={PROFILES} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /An/ }))
    expect(onSelect).toHaveBeenCalledWith('b')
    expect(onSelect).toHaveBeenCalledOnce()
  })
})
