import phrases from './phrases.vi.json'

export type PhraseKey = keyof typeof phrases

/** A UI phrase's Vietnamese text, from the single phrase catalogue (`phrases.vi.json`)
 * `backend/hoctap/builder/stages/speak.py` scans to pre-synthesise audio for. */
export function phrase(key: PhraseKey): string {
  return phrases[key]
}
