import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import SolutionPanel from './SolutionPanel'

const steps = ['Bước 1', 'Bước 2', 'Bước 3', 'Bước 4']

describe('SolutionPanel', () => {
  it('renders only the first revealedCount steps, the rest absent from the DOM', () => {
    render(<SolutionPanel steps={steps} revealedCount={2} />)
    expect(screen.getByText('Bước 1')).toBeInTheDocument()
    expect(screen.getByText('Bước 2')).toBeInTheDocument()
    expect(screen.queryByText('Bước 3')).not.toBeInTheDocument()
    expect(screen.queryByText('Bước 4')).not.toBeInTheDocument()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('renders nothing when revealedCount is 0', () => {
    render(<SolutionPanel steps={steps} revealedCount={0} />)
    expect(screen.queryAllByRole('listitem')).toHaveLength(0)
  })

  it('renders every step when revealedCount covers them all', () => {
    render(<SolutionPanel steps={steps} revealedCount={4} />)
    expect(screen.getAllByRole('listitem')).toHaveLength(4)
  })
})
