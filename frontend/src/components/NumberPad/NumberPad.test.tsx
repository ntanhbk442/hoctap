import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import NumberPad from './NumberPad'

describe('NumberPad', () => {
  it('emits a digit callback for each of 0-9', () => {
    const onDigit = vi.fn()
    render(<NumberPad onDigit={onDigit} onBackspace={vi.fn()} />)
    for (const digit of ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']) {
      fireEvent.click(screen.getByRole('button', { name: digit }))
    }
    expect(onDigit.mock.calls.map((c) => c[0]).sort()).toEqual(
      ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'].sort(),
    )
  })

  it('emits backspace', () => {
    const onBackspace = vi.fn()
    render(<NumberPad onDigit={vi.fn()} onBackspace={onBackspace} />)
    fireEvent.click(screen.getByRole('button', { name: 'Xoá' }))
    expect(onBackspace).toHaveBeenCalledOnce()
  })

  it('shows the comma key by default and emits its callback', () => {
    const onComma = vi.fn()
    render(<NumberPad onDigit={vi.fn()} onBackspace={vi.fn()} onComma={onComma} />)
    fireEvent.click(screen.getByRole('button', { name: 'Dấu phẩy' }))
    expect(onComma).toHaveBeenCalledOnce()
  })

  it('hides the comma key when showComma is false (grades 1-3)', () => {
    render(<NumberPad onDigit={vi.fn()} onBackspace={vi.fn()} showComma={false} />)
    expect(screen.queryByRole('button', { name: 'Dấu phẩy' })).not.toBeInTheDocument()
  })

  it('renders every key at least touch-min, at the 80px key size', () => {
    render(<NumberPad onDigit={vi.fn()} onBackspace={vi.fn()} />)
    for (const button of screen.getAllByRole('button')) {
      expect(button.style.width).toBe('80px')
      expect(button.style.height).toBe('80px')
    }
  })

  it('the expression pad adds + − × : ( ) / keys, all 80px, and emits the symbol', () => {
    const onSymbol = vi.fn()
    render(<NumberPad onDigit={vi.fn()} onBackspace={vi.fn()} expression onSymbol={onSymbol} />)
    for (const name of ['Cộng', 'Trừ', 'Nhân', 'Chia', 'Mở ngoặc', 'Đóng ngoặc', 'Gạch phân số']) {
      fireEvent.click(screen.getByRole('button', { name }))
    }
    expect(onSymbol.mock.calls.map((c) => c[0])).toEqual(['+', '−', '×', ':', '(', ')', '/'])
    expect(screen.getByRole('button', { name: 'Dấu phẩy' })).toBeInTheDocument()
    for (const button of screen.getAllByRole('button')) {
      expect(button.style.width).toBe('80px')
    }
  })
})
