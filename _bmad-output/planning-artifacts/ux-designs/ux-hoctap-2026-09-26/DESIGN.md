---
name: Học Tập
description: Spoken, touch-first maths practice for a grade-1 child. Bright, flat, rounded and friendly, in the spirit of Khan Academy Kids and Duolingo. No mascot.
status: final
created: 2026-09-26
updated: 2026-09-26
sources:
  - ../../prds/prd-hoctap-2026-09-26/prd.md
  - ../../briefs/brief-hoctap-2026-09-26/brief.md
colors:
  surface-base: '#FFF8EC'
  surface-raised: '#FFFFFF'
  surface-sunken: '#F3EBDD'
  ink-primary: '#2B2D42'
  ink-secondary: '#5C6178'
  ink-on-color: '#FFFFFF'
  primary: '#1971C2'
  primary-pressed: '#145591'
  primary-soft: '#D0EBFF'
  success: '#2A7D3A'
  success-pressed: '#1E5E2B'
  success-soft: '#D3F9D8'
  retry: '#C2410C'
  retry-soft: '#FFE8CC'
  hint: '#7048E8'
  hint-soft: '#EDE7FF'
  star: '#FAB005'
  star-outline: '#946800'
  progress-todo: '#978770'
  streak: '#FF6B2C'
  slot-border: '#6B7A90'
  slot-border-active: '#1971C2'
  parent-surface: '#F8F9FA'
  parent-border: '#DEE2E6'
typography:
  display:
    fontFamily: Nunito
    fontSize: 40px
    fontWeight: 800
    lineHeight: 1.2
  instruction:
    fontFamily: Nunito
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.35
  answer:
    fontFamily: Nunito
    fontSize: 40px
    fontWeight: 800
    lineHeight: 1
  body:
    fontFamily: Nunito
    fontSize: 22px
    fontWeight: 600
    lineHeight: 1.45
  label:
    fontFamily: Nunito
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.2
  parent-body:
    fontFamily: Nunito
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.5
  parent-heading:
    fontFamily: Nunito
    fontSize: 22px
    fontWeight: 800
    lineHeight: 1.3
rounded:
  sm: 12px
  md: 20px
  lg: 28px
  full: 9999px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 24px
  '6': 32px
  '7': 48px
  touch-min: 64px
  key: 80px
components:
  button-primary:
    background: '{colors.primary}'
    pressed: '{colors.primary-pressed}'
    text: '{colors.ink-on-color}'
    typography: '{typography.label}'
    radius: '{rounded.full}'
    minHeight: '{spacing.touch-min}'
  button-check:
    background: '{colors.success}'
    pressed: '{colors.success-pressed}'
    text: '{colors.ink-on-color}'
    radius: '{rounded.full}'
    minHeight: 72px
  speaker-button:
    background: '{colors.primary-soft}'
    icon: '{colors.primary}'
    size: '{spacing.touch-min}'
    radius: '{rounded.full}'
  card-home:
    background: '{colors.surface-raised}'
    radius: '{rounded.lg}'
    padding: '{spacing.5}'
    minHeight: 160px
  answer-slot:
    background: '{colors.surface-raised}'
    border: '{colors.slot-border}'
    borderActive: '{colors.slot-border-active}'
    borderWidth: 3px
    radius: '{rounded.sm}'
    size: 80px
    typography: '{typography.answer}'
  numpad-key:
    background: '{colors.surface-raised}'
    text: '{colors.ink-primary}'
    size: '{spacing.key}'
    radius: '{rounded.md}'
    typography: '{typography.answer}'
  choice-chip:
    background: '{colors.surface-raised}'
    selected: '{colors.primary-soft}'
    border: '{colors.slot-border}'
    radius: '{rounded.md}'
    minHeight: 88px
  feedback-correct:
    background: '{colors.success-soft}'
    accent: '{colors.success}'
  feedback-retry:
    background: '{colors.retry-soft}'
    accent: '{colors.retry}'
  hint-bubble:
    background: '{colors.hint-soft}'
    accent: '{colors.hint}'
    radius: '{rounded.md}'
  badge:
    background: '{colors.surface-raised}'
    ring: '{colors.star}'
    ringOutline: '{colors.star-outline}'
    size: 96px
    radius: '{rounded.full}'
  progress-dot:
    done: '{colors.success}'
    current: '{colors.primary}'
    todo: '{colors.progress-todo}'
    size: 16px
---

## Brand & Style

Học Tập should feel like a friendly game that happens to be homework. The references are Khan Academy Kids and Duolingo: bright flat colour, chunky rounded shapes, big friendly type, and a small celebration for every right answer. There's no mascot. Warmth comes from colour, sound and motion instead. The child's screens are loud and simple. The Parent Area is the same family, but quieter and denser, like the grown-up's page at the back of the book. [ASSUMPTION: palette and type chosen for you; tweak freely]

## Colors

- **Warm cream (`surface-base`)** is the canvas for every child screen. It's softer than white for evening use. Problems sit on **white** (`surface-raised`) cards.
- **Sky blue (`primary`)** is for navigation and actions: the speaker button, "Tiếp" (next), the active answer slot. It echoes the Archimedes book blue.
- **Green (`success`)** means *correct* and the ✔ Kiểm tra (check) button. It is never used for decoration.
- **Orange (`retry`)** means *not yet*. There is deliberately **no red** on child screens: a wrong answer is "chưa đúng" (not yet), not a failure.
- **Purple (`hint`)** belongs only to Hints and Concept Guides, so the child learns that "purple = help".
- **Gold (`star`)** and **flame orange (`streak`)** are reserved for rewards.
- **Parent Area** uses `parent-surface` and `parent-border` greys with the same blue for actions.

Meaning is never carried by colour alone. Every state also has an icon (✔, ↻, 💡) and a sound.

**Contrast (WCAG 2.2 AA, checked):**
- White text on the coloured backgrounds: `primary` 5.0:1, `success` 5.1:1, `retry` 5.2:1, `hint` 5.6:1. The pressed colours are above 7:1.
- `ink-secondary` on the cream background is 5.8:1.
- UI boundaries: `slot-border` on white is 4.4:1 and `progress-todo` on cream is 3.3:1. Both are at least 3:1.
- Gold `star` is 1.9:1 against the background, which is too low on its own, so every star icon carries a 2px `star-outline` border (4.7:1).
- Soft backgrounds (`*-soft`) always carry `ink-primary` text, never white.

## Typography

**Nunito** is used everywhere. It's rounded, very readable for early readers, and has full Vietnamese diacritics. It is self-hosted, so it works offline (NFR-1).
- `display` (40px/800) is for the large `<` `=` `>` symbols on `compare` choice chips and for big numbers in Session summary counts.
- `answer` (40px/800) is for digits in answer slots and on the number pad.
- `instruction` (28px/700) is for the one instruction line.
- `body` (22px/600) is for Hints and Solutions.
- `label` (18px/700) is for button text.
- Parent screens use `parent-body` (16px/500) and `parent-heading` (22px/800).
- Child screens never go below 18px.
- Maths overlines (`2a4b` with a bar over it) use CSS `text-decoration: overline` in the same font.

## Layout & Spacing

- The spacing scale is 4, 8, 12, 16, 24, 32 and 48px.
- **The minimum touch target is `touch-min` (64px)** (NFR-3). Number-pad keys and answer slots are `key` (80px).
- The child's Problem screen uses three fixed zones: the **top bar** (back, progress dots, 🔊), the **work area** (the problem, centred), and the **action bar** (number pad or controls, plus ✔ Kiểm tra) along the bottom edge in portrait, or on the right in landscape, where a thumb can reach it.
- There is one column on child screens. The Parent Area uses a two-column dashboard on the PC and one column on the tablet.

## Elevation & Depth

Depth is flat but "chunky". Cards and buttons have a solid bottom edge 4px deep in a darker tone of their own colour, instead of a soft shadow. When pressed, the edge drops to 0 and the element moves down 4px, which feels like a physical button. The Parent Area uses 1px borders and no edge.

## Shapes

Corners are big and soft throughout:
- `rounded.lg` (28px) for Home cards.
- `rounded.md` (20px) for choice chips, number-pad keys and Hint bubbles.
- `rounded.sm` (12px) for answer slots, because a box shape reads as "write here".
- `rounded.full` for buttons, the speaker button and badges.
- There are no sharp corners on child screens.
- Cropped book images keep a `rounded.sm` (12px) radius and a 2px `slot-border` frame, so they look like part of the app and not a pasted scan.

## Components

- **Speaker button 🔊** — a round `primary-soft` button with a blue icon. It pulses gently while audio is playing. It appears next to every instruction, option, Hint and Solution.
- **Buttons** — pill-shaped (`rounded.full`). Actions such as "Tiếp" (next) use `button-primary`: blue, `label` text, at least `touch-min` tall. ✔ Kiểm tra (check) uses `button-check`: green, at least 72px tall.
- **Home card** — a large white card with an icon, a title (`label`) and its own 🔊. "Bài hôm nay" (today's lesson) is double width, and its 4px chunky bottom edge is `primary-pressed` blue instead of the usual darker tone of white.
- **Answer slot** — a white box with a 3px grey border that turns blue when active. A correct answer turns it green with a ✔ tick; a wrong one shakes it and turns it orange.
- **Number pad** — the keys 0–9 and ⌫, plus a comma for grades 4–5 only, in a 3×4 grid of 80px keys.
- **Choice chip** — for `compare` (`<` `>` `=` in `display` size), `multiple_choice` and `image_select`. It turns soft blue (`primary-soft`) when selected.
- **Feedback banner** — slides up from the bottom. Correct: soft green (`success-soft`), "Đúng rồi!" (correct!) and stars. Wrong: soft orange (`retry-soft`), "Chưa đúng, thử lại nhé!" (not yet, try again!).
- **Hint bubble** — soft purple (`hint-soft`) with 💡, the Hint text in `body`, and 🔊.
- **Progress dots** — one dot per Problem in the Session: green when done, blue for the current one, `progress-todo` rings for the rest.
- **Badge** — a 96px round medal with a gold ring, an icon and a short label ("Hoàn thành Tuần 1" — finished week 1). A newly earned badge pops onto the Session summary. The latest 3 badges show on Home, and all of them are in "Huy hiệu của em" (your badges).
- **Star burst and streak flame** — gold stars fly from the Problem into the counter at the top. The flame appears on Home and in the summary.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Orange "chưa đúng" with a retry icon | Red, ✗, or "Sai!" (wrong!) on child screens |
| One instruction line, always with 🔊 | Paragraphs of text for the child |
| 64px or larger targets, with 80px keys | Small links or icon-only buttons without a label and 🔊 |
| Purple only for help, green only for correct | Decorative use of the colours that carry meaning |
| Book images framed like app content | Full raw page scans on child screens (except `fallback`) |
| Celebrate with stars, confetti and a chime | Timers, lives or hearts that can be lost, leaderboards |
