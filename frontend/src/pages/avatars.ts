import type { Avatar } from '../api/client'

export const AVATARS: ReadonlyArray<{ key: Avatar; label: string; emoji: string }> = [
  { key: 'cat', label: 'Mèo', emoji: '🐱' },
  { key: 'dog', label: 'Chó', emoji: '🐶' },
  { key: 'rabbit', label: 'Thỏ', emoji: '🐰' },
  { key: 'bear', label: 'Gấu', emoji: '🐻' },
  { key: 'fox', label: 'Cáo', emoji: '🦊' },
  { key: 'panda', label: 'Gấu trúc', emoji: '🐼' },
]

export const GRADES = [1, 2, 3, 4, 5] as const

export const PIN_PATTERN = /^[0-9]{4}$/
