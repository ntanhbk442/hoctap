import './ProgressDots.css'

export type DotState = 'done' | 'current' | 'todo'

export interface ProgressDotsProps {
  dots: DotState[]
}

const LABEL: Record<DotState, string> = {
  done: 'đã xong',
  current: 'đang làm',
  todo: 'chưa làm',
}

/** One dot per Problem in the Session (`progress-dot` spec): green when done, blue for the
 * current one, `progress-todo` rings for the rest. */
export default function ProgressDots({ dots }: ProgressDotsProps) {
  return (
    <ol className="progress-dots" aria-label="Tiến độ">
      {dots.map((state, index) => (
        <li
          key={index}
          className={`progress-dot progress-dot-${state}`}
          aria-label={`Bài ${index + 1}: ${LABEL[state]}`}
        />
      ))}
    </ol>
  )
}
