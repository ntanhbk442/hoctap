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
