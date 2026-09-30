# Code review: Epic 2, first half (Stories 2.1-2.6), 2026-09-30

Range `9f19102..ed8fca3`, backend and frontend **source only** (tests, lockfiles, generated files and binary assets left out of the diff; the Verification Gap layer read tests from the repo). Four independent layers reviewed against the six story specs. Claims that mattered were checked against the code; reviewer severities were disregarded. Stories 2.7-2.11 are reviewed separately.

## Decision needed

- [ ] [Review][Decision] **Staged help counts wrong attempts across all history and never resets** [medium] `sessions.py:_count_prior_wrong` counts a Part's wrong attempts in every Session for the Profile. Once a Part has been missed anywhere, its next wrong attempt in any later Session releases the Solution immediately (the Hint phase is skipped, and it scores 0 Stars), including when the child is re-trying it through the Retry Queue. This follows Story 2.5's frozen wording ("Profile-wide, per AD-6"). Options: count only within the current Session, so each Session gives Hint then Solution / keep Profile-wide.
- [ ] [Review][Decision] **"Học tiếp" always points at the first Lesson, whatever the child has done** [medium] `content/library.py:home_lesson` returns the first Lesson with a visible Problem and ignores progress; `get_home` uses it as is. Story 2.3 specified this as the placeholder. Nothing since made it progress-aware, so a child who finishes Lesson 1 still sees it as "continue". Options: pick the first Lesson that still has an unattempted Problem (falling back to the first when everything is done) / keep.

## Patch

- [ ] [Review][Patch] **"Kiểm tra" does nothing after a wrong answer if the answer is left unchanged** [medium] `ProblemPlayer.tsx:handleCheck` returns silently while `submittingRef` is true; in the `wrong-hint` phase the ref is only reset by an edit (`retryIfSettled`). The button is enabled but dead. Reset it when the button is pressed in that phase.
- [ ] [Review][Patch] **The hint bubble's 🔊 replay does nothing** [medium] `ProblemPlayer.tsx:660` renders `<HintBubble text=… />` without `onSpeak`. The hint is spoken once automatically; the child (a pre-reader) cannot replay it, against UX-DR7 ("replay is free"). Wire `onSpeak` to speak the hint.
- [ ] [Review][Patch] **Player timers not cleared on unmount** [low] The 700 ms correct-advance and 400 ms wrong-feedback timeouts in `PartPlayer` can fire after the child leaves. Same fix as the quiz timer in Epic 3.
- [ ] [Review][Patch] **Test gaps** [medium] (a) `imageUrl` in `ProblemPlayer.tsx` maps `crop_urls` to images by position and no test asserts an `<img src>`, with or without multi-page `source_pages`; (b) the `POST /sessions/{id}/events` lock-retry loop and the 30 s `busy_timeout` are untested; (c) the `speak-missing` cloud spend cap (`--max-total-usd`, `--yes-spend`, exit code 1 on failures) is not exercised through the CLI; (d) `get_bundle`'s hard-coded voice is not pinned to the configured `tts_voice_id`.
- [ ] [Review][Patch] **`speak-missing` robustness** [low] `tts_client.py` (Google) catches only `GoogleAPICallError` and `OSError`, so missing credentials or a retry error abort the whole run; an empty audio response is written as a zero-byte mp3 that later runs treat as done. Catch broadly per key and record empty audio as a failure.
- [ ] [Review][Patch] **Double-tapping "Học tiếp" or "Luyện lại" can start two Sessions** [low] Same fix the Epic 4 patches apply to the assignment card (`isPending` guard); apply to the other Home cards after those land.

## Deferred

- [x] [Review][Defer] **Backend and frontend disagree if a Problem lists the same source page twice** [medium, unverified] `content/assets.py` builds page crops from the un-deduplicated page list while `imageUrl` counts a `Set`, so the image index could be off by the duplicates. — deferred: needs a real Problem with a repeated page number to confirm.
- [x] [Review][Defer] **Bundle audio uses a hard-coded voice ID (`DEFAULT_VOICE_ID`, duplicated in `speech.ts`)** [medium if the voice is ever changed] Changing `tts_voice_id` in config would silently break all read-aloud audio. — deferred: the default voice works; full fix means plumbing the configured voice through the bundle and having the player use the bundle's audio map instead of recomputing keys. The patch above only pins the default.

## Rejected

- Retry Queue "never re-adds a resolved Problem" (2 layers): false since Epic 3, `_grade_and_stage` calls `add_retry_item` on every wrong attempt.
- Solution released via crafted attempts without the child seeing the hint; resend with a changed payload: by design, the client is untrusted only for what it can already see, and a resend returns the stored verdict.
- Ownership check compares a client-supplied `profile_id`: the app has no child authentication by design (LAN family app, profiles are listed openly).
- Numeric grading uses its own `_lenient_number` instead of `parse_number()`: recorded in Story 2.5's Spec Change Log; the fix would edit the frozen spec.
- Story 2.5 touched 2.4's bundle, added the retry loop and the 30 s `busy_timeout`: reasoned in comments; not a defect.
- Decimal comma / minus keys missing on the keypad, unplaced slots, empty `parts`: grade-1 content has neither; Epic 6 covers expression input.
- `crypto.subtle` missing on plain http: the app is served over HTTPS on the LAN (Story 1.11).
- Non-canonical UUID spellings bypass idempotency: needs a hand-made client; the app sends canonical ids.
- VACUUM renumbering rowids: nothing in the codebase runs VACUUM.
- Event batch and payload size caps, other `IntegrityError` causes, unvalidated `occurred_at`: low; single-family LAN.
- Grader duplicate-key edge cases, `speak()` overlapping clips, `speak('')`, timer id churn, ✔ glyph missing, progress dots unused, local star count: cosmetic or specified.
- Missing sound-effect tests and `ENGINE_NAMES` drift test: low, one-line follow-ups.
- No 🔊 next to instructions in the player: Story 2.9 (next half) adds audio for instructions; re-check there.
- Health indicator removed from Home; unbounded `google-cloud-texttospeech` dependency; orphaned mp3 cleanup: low.

## Decisions resolved (2026-09-30, by Anh) -> now patches

1. Staged help: count a Part's wrong attempts only within the current Session (first miss gives the Hint, second gives the Solution; a fresh Session starts over). Reverses Story 2.5's Profile-wide wording. Quiz Sessions stay excluded.
2. "Học tiếp": pick the first Lesson that still has an unattempted visible Problem, falling back to the first Lesson when everything is done. Reverses Story 2.3's "always the first Lesson" placeholder.

Patch handling chosen: apply every patch.
