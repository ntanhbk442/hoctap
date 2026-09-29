import './widgets.css'

/** A Part type outside the 5 basic ones this story implements (`order`, `match`, the
 * Story 2.7/2.8 types, ...) -- a clear "chưa hỗ trợ" placeholder, never a crash. Expected
 * sequencing (later stories add these), not a bug (Boundaries & Constraints). */
export default function UnsupportedWidget({ type }: { type: string }) {
  return (
    <div className="widget-unsupported" role="status">
      <p>Phần bài tập này ({type}) chưa được hỗ trợ trên máy tính bảng/PC.</p>
    </div>
  )
}
