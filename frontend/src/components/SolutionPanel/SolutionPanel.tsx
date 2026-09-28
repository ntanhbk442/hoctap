import './SolutionPanel.css'

export interface SolutionPanelProps {
  steps: string[]
  /** How many steps are revealed so far. Unrevealed steps are not rendered at all (not just
   * hidden) — the real timing/reveal-one-at-a-time behaviour is the grading stories' job. */
  revealedCount: number
}

/** A stepped reveal container (`Solution panel` behaviour, EXPERIENCE.md). */
export default function SolutionPanel({ steps, revealedCount }: SolutionPanelProps) {
  const revealed = steps.slice(0, Math.max(0, revealedCount))
  return (
    <ol className="solution-panel" aria-label="Các bước giải">
      {revealed.map((step, index) => (
        <li key={index} className="solution-panel-step">
          {step}
        </li>
      ))}
    </ol>
  )
}
