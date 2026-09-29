import { KEY_SIZE } from '../../styles/dimensions'
import './NumberPad.css'

export interface NumberPadProps {
  onDigit: (digit: string) => void
  onBackspace: () => void
  onComma?: () => void
  /** Grades 4–5 get a comma key (FR-9); grades 1–3 don't. Defaults to shown. */
  showComma?: boolean
  /** Additive (Story 2.6 finding #4): inert-looking while a submit is in flight or feedback
   * is settling. Optional and defaults to enabled so every existing call site is unchanged. */
  disabled?: boolean
}

const DIGIT_ROWS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
]

function Key({
  label,
  ariaLabel,
  onClick,
  disabled,
}: {
  label: string
  ariaLabel?: string
  onClick: () => void
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      className="numpad-key"
      style={{ width: KEY_SIZE, height: KEY_SIZE, minWidth: KEY_SIZE, minHeight: KEY_SIZE }}
      aria-label={ariaLabel ?? label}
      disabled={disabled}
      onClick={onClick}
    >
      {label}
    </button>
  )
}

/** A 3×4 grid of `numpad-key`-styled keys: 0–9, ⌫, and an optional comma key. No numeric
 * logic here — that's the widget layer in later stories. */
export default function NumberPad({
  onDigit,
  onBackspace,
  onComma,
  showComma = true,
  disabled = false,
}: NumberPadProps) {
  return (
    <div className="numpad" role="group" aria-label="Bàn phím số">
      {DIGIT_ROWS.map((row) =>
        row.map((digit) => (
          <Key key={digit} label={digit} disabled={disabled} onClick={() => onDigit(digit)} />
        )),
      )}
      {showComma ? (
        <Key label="," ariaLabel="Dấu phẩy" disabled={disabled} onClick={() => onComma?.()} />
      ) : (
        <span className="numpad-filler" aria-hidden="true" />
      )}
      <Key label="0" disabled={disabled} onClick={() => onDigit('0')} />
      <Key label="⌫" ariaLabel="Xoá" disabled={disabled} onClick={onBackspace} />
    </div>
  )
}
