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
  /** Story 6.1: the `expression_input` keypad -- the number pad plus + − × : ( ) and `/`
   * (same 80 px keys, one extra grid column each side). The comma key is always shown then.
   * `onSymbol` receives the typed character. Additive: absent, the pad is unchanged. */
  expression?: boolean
  onSymbol?: (symbol: string) => void
}

/** Operator/parenthesis keys of the expression pad: [symbol, aria-label]. Column 4 then
 * column 5 of the 5-column grid, top to bottom. */
const OPERATOR_COLUMN: [string, string][] = [
  ['+', 'Cộng'],
  ['−', 'Trừ'],
  ['×', 'Nhân'],
  [':', 'Chia'],
]
const GROUP_COLUMN: [string, string][] = [
  ['(', 'Mở ngoặc'],
  [')', 'Đóng ngoặc'],
  ['/', 'Gạch phân số'],
]

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
  expression = false,
  onSymbol,
}: NumberPadProps) {
  if (expression) {
    const sym = (entry: [string, string]) => (
      <Key
        key={entry[0]}
        label={entry[0]}
        ariaLabel={entry[1]}
        disabled={disabled}
        onClick={() => onSymbol?.(entry[0])}
      />
    )
    const digit = (d: string) => (
      <Key key={d} label={d} disabled={disabled} onClick={() => onDigit(d)} />
    )
    return (
      <div className="numpad numpad-expression" role="group" aria-label="Bàn phím biểu thức">
        {digit('1')}
        {digit('2')}
        {digit('3')}
        {sym(OPERATOR_COLUMN[0])}
        {sym(GROUP_COLUMN[0])}
        {digit('4')}
        {digit('5')}
        {digit('6')}
        {sym(OPERATOR_COLUMN[1])}
        {sym(GROUP_COLUMN[1])}
        {digit('7')}
        {digit('8')}
        {digit('9')}
        {sym(OPERATOR_COLUMN[2])}
        {sym(GROUP_COLUMN[2])}
        <Key label="," ariaLabel="Dấu phẩy" disabled={disabled} onClick={() => onComma?.()} />
        {digit('0')}
        <Key label="⌫" ariaLabel="Xoá" disabled={disabled} onClick={onBackspace} />
        {sym(OPERATOR_COLUMN[3])}
        <span className="numpad-filler" aria-hidden="true" />
      </div>
    )
  }
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
