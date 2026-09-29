// Short feedback sound effects for the Problem player (Story 2.6): a "chime" on a correct
// Attempt, a "boop" on a wrong one (this story's frozen Intent). These are fixed clips (not
// TTS), so they don't go through `speech.ts`'s `speak()`/`speechKey()` pipeline -- but they
// follow the exact same silent-no-op-on-failure contract as `speak()` (see its own docstring):
// no `Audio` support (tests/SSR), no file yet at this path, or blocked playback all end in the
// same no-op, never a thrown/rejected error the caller has to guard against. No sfx assets
// ship with this story (asset generation is a builder-pipeline concern, out of this story's
// frontend-only scope, see this story's Implementation Notes) -- until one exists at the path
// below, both calls are inert, exactly like `speak()` before a phrase's clip is synthesised.
const ASSETS_URL = '/assets-data'

async function playClip(name: string): Promise<void> {
  try {
    const audio = new Audio(`${ASSETS_URL}/sfx/${name}.mp3`)
    await audio.play()
  } catch {
    // Silent no-op -- see the module docstring.
  }
}

export function playChime(): Promise<void> {
  return playClip('chime')
}

export function playBoop(): Promise<void> {
  return playClip('boop')
}
