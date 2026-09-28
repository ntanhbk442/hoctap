import { describe, expect, it } from 'vitest'
import { speechKey, speechText, speechUrl } from './speech'

// Regression guard against `speechText()`/`speechKey()` drifting from their Python source
// of truth (`backend/hoctap/content/speech.py`'s `speech_text()`/`speech_key()`) -- the
// same class of gap Story 2.2 was flagged for with its own hand-synced normaliser. Every
// case (input, expected `speechText()` output, and for the key cases, the expected hash)
// is lifted directly from `backend/tests/test_speech.py`'s existing fixtures/expectations.

describe('speechText (ported from content.speech.speech_text)', () => {
  it('reads a comparison operator', () => {
    expect(speechText('3 < 5')).toBe('3 bé hơn 5')
  })

  it('reads an arithmetic operator', () => {
    expect(speechText('1 + 2')).toBe('1 cộng 2')
  })

  it('reads \\overline{...} digit by digit', () => {
    expect(speechText('\\overline{2a4b}')).toBe('số hai a bốn b')
  })

  it('reads \\frac{a}{b} as "a phần b"', () => {
    expect(speechText('\\frac{1}{2}')).toBe('một phần hai')
  })

  it('passes plain digits and words through unchanged', () => {
    expect(speechText('Con có 5 quả táo')).toBe('Con có 5 quả táo')
  })
})

describe('speechKey (ported from content.speech.speech_key)', () => {
  it('matches the backend hash for a known (text, voice_id) pair', async () => {
    // python -c "from hoctap.content.speech import speech_key; \
    //   print(speech_key('3 < 5', 'vi-VN-HoaiMyNeural'))"
    expect(await speechKey('3 < 5', 'vi-VN-HoaiMyNeural')).toBe('3d0b45f5f9b8ef1c')
  })

  it('matches the backend hash for another known pair', async () => {
    expect(await speechKey('xin chào', 'vi-VN-HoaiMyNeural')).toBe('d3acdc0fbc87b28f')
  })

  // Every one of the 9 operators in `_OPERATOR_WORDS`/`OPERATOR_WORDS`, each hash
  // computed from the real Python source of truth, e.g.:
  //   python -c "from hoctap.content.speech import speech_key; \
  //     print(speech_key('3 > 5', 'vi-VN-HoaiMyNeural'))"
  // A silent divergence on any single operator (a typo'd word, a swapped char) would
  // change that operator's hash and fail here.
  it.each([
    ['<', '3 < 5', '3d0b45f5f9b8ef1c'],
    ['>', '3 > 5', '3f75f726e07cbcdd'],
    ['=', '3 = 5', '3844ec4a5dbd2bfa'],
    ['+', '1 + 2', '90c37ed6c9de6817'],
    ['-', '3 - 1', '4c527e3710edd365'],
    ['×', '2 × 3', '1406331ac1423e4c'],
    ['*', '2 * 3', '1406331ac1423e4c'],
    ['÷', '6 ÷ 2', 'ca92f8d077f8d84b'],
    ['/', '6 / 2', 'ca92f8d077f8d84b'],
  ])('matches the backend hash for the "%s" operator', async (_op, text, expected) => {
    expect(await speechKey(text, 'vi-VN-HoaiMyNeural')).toBe(expected)
  })

  it('is stable for the same input', async () => {
    const a = await speechKey('3 < 5', 'vi-VN-HoaiMyNeural')
    const b = await speechKey('3 < 5', 'vi-VN-HoaiMyNeural')
    expect(a).toBe(b)
  })

  it('changes when the text changes', async () => {
    const a = await speechKey('3 < 5', 'vi-VN-HoaiMyNeural')
    const b = await speechKey('3 > 5', 'vi-VN-HoaiMyNeural')
    expect(a).not.toBe(b)
  })

  it('changes when the voice changes', async () => {
    const a = await speechKey('3 < 5', 'vi-VN-HoaiMyNeural')
    const b = await speechKey('3 < 5', 'vi-VN-NamMinhNeural')
    expect(a).not.toBe(b)
  })

  it('is 16 hex chars', async () => {
    const key = await speechKey('xin chào', 'vi-VN-HoaiMyNeural')
    expect(key).toHaveLength(16)
    expect(() => BigInt(`0x${key}`)).not.toThrow()
  })
})

describe('speechUrl', () => {
  it('mirrors content.assets/content.speech\'s URL scheme', () => {
    expect(speechUrl('abc123')).toBe('/assets-data/audio/abc123.mp3')
  })
})
