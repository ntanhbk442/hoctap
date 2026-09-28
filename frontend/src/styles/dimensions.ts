// Mirrors DESIGN.md's spacing.touch-min / spacing.key (tokens.css's --space-touch-min /
// --space-key). Components apply these as inline style, in addition to the matching CSS
// class, because jsdom (our test environment) does not resolve CSS custom properties in
// `getComputedStyle` — so a component's test can assert the rendered touch-target size
// deterministically without depending on that. `tokens.test.ts` asserts these two stay equal
// to the parsed DESIGN.md values, so a spacing change can't make this file silently stale.
export const TOUCH_MIN = 64
export const KEY_SIZE = 80

// Mirrors DESIGN.md's components.choice-chip.minHeight (88px, a literal in DESIGN.md, not a
// `{spacing.*}` token reference — so it isn't in tokens.css and isn't covered by the
// touch-min/key sync test above).
export const CHOICE_CHIP_MIN_HEIGHT = 88
