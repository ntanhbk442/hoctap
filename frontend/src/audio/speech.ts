// Frontend counterpart of `backend/hoctap/content/speech.py`'s `speech_text()`/
// `speech_key()`/`speech_url()`. This story (2.3) adds no new TTS/audio-generation work --
// it only needs to resolve the URL of an *already synthesised* clip (the builder's `speak`
// stage, gated behind real spend, is what writes the mp3 files under `assets-data/audio/`).
// A phrase not yet synthesised simply has no file yet; `speak()` below is a silent no-op
// in that case, never a crash.
//
// `DEFAULT_VOICE_ID` mirrors `Settings.tts_voice_id`'s default (`backend/hoctap/config.py`)
// -- there is no endpoint exposing it, so this is a deliberate, documented duplication (see
// this story's Implementation Notes), not a new backend concept.
import { playKey } from './player'

export const DEFAULT_VOICE_ID = 'vi-VN-HoaiMyNeural'

const ASSETS_URL = '/assets-data'

// A digit-by-digit port of `speech_text()`'s v1 normaliser: only what the UI phrase
// catalogue's plain Vietnamese strings need (NFC + whitespace collapse); the
// `\overline{}`/`\frac{}{}`/operator handling is included for parity with Problem text,
// even though no current UI phrase uses that notation.
const DIGIT_WORDS: Record<string, string> = {
  '0': 'không',
  '1': 'một',
  '2': 'hai',
  '3': 'ba',
  '4': 'bốn',
  '5': 'năm',
  '6': 'sáu',
  '7': 'bảy',
  '8': 'tám',
  '9': 'chín',
}

const OPERATOR_WORDS: ReadonlyArray<readonly [string, string]> = [
  ['<', 'bé hơn'],
  ['>', 'lớn hơn'],
  ['=', 'bằng'],
  ['+', 'cộng'],
  ['-', 'trừ'],
  ['×', 'nhân'],
  ['*', 'nhân'],
  ['÷', 'chia'],
  ['/', 'chia'],
]

const OVERLINE_RE = /\\overline\{([0-9A-Za-z]*)\}/g
const FRAC_RE = /\\frac\{([0-9A-Za-z]*)\}\{([0-9A-Za-z]*)\}/g

function spell(chars: string): string {
  return chars
    .split('')
    .map((ch) => DIGIT_WORDS[ch] ?? ch)
    .join(' ')
}

/** The Vietnamese read-aloud text for `text` -- must match `speech_text()` for any text
 * this story's phrases could plausibly contain. */
export function speechText(text: string): string {
  let value = text.normalize('NFC')
  value = value.replace(OVERLINE_RE, (_m, body: string) => `số ${spell(body)}`)
  value = value.replace(FRAC_RE, (_m, num: string, den: string) => `${spell(num)} phần ${spell(den)}`)
  for (const [char, word] of OPERATOR_WORDS) {
    if (value.includes(char)) value = value.split(char).join(` ${word} `)
  }
  return value
    .split(/\s+/)
    .filter(Boolean)
    .join(' ')
    .normalize('NFC')
}

/** sha256(normalised text + voice id), first 16 hex chars -- matches `speech_key()`. */
export async function speechKey(text: string, voiceId: string = DEFAULT_VOICE_ID): Promise<string> {
  const normalized = speechText(text)
  const bytes = new TextEncoder().encode(normalized + voiceId)
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const hex = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
  return hex.slice(0, 16)
}

export function speechUrl(key: string): string {
  return `${ASSETS_URL}/audio/${key}.mp3`
}

/**
 * Plays the given text's pre-synthesised clip, if one exists (SpeakerButton tap/long-press
 * wiring, Story 2.3). Never throws and never rejects visibly: no `Audio`/`crypto.subtle`
 * support (tests), no audio file yet (not synthesised), or playback being blocked all end
 * in the same silent no-op.
 *
 * Story 2.9: internally upgraded to go through `audio/player.ts`'s single shared `<audio>`
 * element (stop-previous-on-new-clip, stop-on-unmount via the player's `stop()`, missing-file
 * detection via the element's own `error` event) -- this function's signature/behaviour for
 * existing callers (HintBubble/SolutionPanel/long-press-to-speak/etc.) is unchanged.
 */
export async function speak(text: string): Promise<void> {
  try {
    const key = await speechKey(text)
    await playKey(key, speechUrl(key))
  } catch {
    // Silent no-op -- see the module docstring.
  }
}
