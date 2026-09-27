import { Link } from 'react-router'
import type { ProblemSummary } from '../../api/client'

/** The badges of a Problem: cần duyệt, xung đột, báo lỗi, đã ẩn, trùng. */
export function Badges({ problem }: { problem: ProblemSummary }) {
  const badges: [boolean, string, string][] = [
    [problem.awaiting_approval, 'cần duyệt', 'badge-review'],
    [problem.conflict, 'xung đột', 'badge-conflict'],
    [problem.report, 'báo lỗi', 'badge-report'],
    [problem.hidden, 'đã ẩn', 'badge-hidden'],
    [problem.duplicate, 'trùng', 'badge-duplicate'],
  ]
  return (
    <span className="badges">
      {badges
        .filter(([on]) => on)
        .map(([, label, cls]) => (
          <span key={label} className={`badge ${cls}`}>
            {label}
          </span>
        ))}
    </span>
  )
}

function problemPath(problemId: string): string {
  return `/parent/review/problems/${encodeURIComponent(problemId)}`
}

export default function ProblemList({ items }: { items: ProblemSummary[] }) {
  return (
    <ul className="problem-list">
      {items.map((p) => (
        <li key={p.problem_id}>
          <Link to={problemPath(p.problem_id)}>
            <strong>{p.display_label}</strong> <span className="problem-id">{p.problem_id}</span>
          </Link>
          <Badges problem={p} />
          {p.instruction && <div className="problem-instruction">{p.instruction}</div>}
        </li>
      ))}
    </ul>
  )
}
