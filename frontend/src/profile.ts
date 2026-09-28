// The child Profile picked for this browser session (Story 2.3's Profile Picker).
//
// No other client-only state convention exists yet anywhere in this codebase (checked:
// no `sessionStorage`/`localStorage` usage before this story), so a plain `sessionStorage`
// key is used, matching Child Profile selection's deliberate no-PIN, no-cookie design
// (`api/profiles.py`'s docstring: "the child picks one without a PIN") -- there is no
// backend session concept for this to hook into.

const STORAGE_KEY = 'hoctap.currentProfileId'

export function getCurrentProfileId(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

export function setCurrentProfileId(id: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Private browsing / storage disabled: the picker is simply shown again next time.
  }
}
