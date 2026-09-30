import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { _resetDbEpochForTests, noteStaleEpoch } from './dbEpoch'
import StaleEpochNotice from './StaleEpochNotice'

afterEach(() => _resetDbEpochForTests())

it('shows the notice once events were discarded and can be dismissed', () => {
  render(<StaleEpochNotice />)
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  act(() => noteStaleEpoch())
  expect(screen.getByRole('status')).toHaveTextContent('khôi phục từ bản sao lưu')
  fireEvent.click(screen.getByRole('button', { name: 'Đã hiểu' }))
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
})
