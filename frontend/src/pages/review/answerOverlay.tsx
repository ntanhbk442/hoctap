import type { ProblemPart } from '../../api/client'

function Regions({
  regions,
  selected,
}: {
  regions: { region_key: string; bbox: number[] }[]
  selected: Set<string>
}) {
  return (
    <>
      {regions.map((r) => {
        const [x0, y0, x1, y1] = r.bbox
        const isSelected = selected.has(r.region_key)
        return (
          <div
            key={r.region_key}
            className={isSelected ? 'answer-region answer-region-selected' : 'answer-region'}
            style={{
              left: `${x0 * 100}%`,
              top: `${y0 * 100}%`,
              width: `${(x1 - x0) * 100}%`,
              height: `${(y1 - y0) * 100}%`,
            }}
          >
            <span className="answer-region-label">{r.region_key}</span>
          </div>
        )
      })}
    </>
  )
}

function Dots({ dots, sequence }: { dots: { n: number; x: number; y: number }[]; sequence: number[] }) {
  const byN = new Map(dots.map((d) => [d.n, d]))
  const points = sequence
    .map((n) => byN.get(n))
    .filter((d): d is { n: number; x: number; y: number } => d !== undefined)
  const polyline = points.map((d) => `${d.x * 100},${d.y * 100}`).join(' ')
  return (
    <>
      {polyline && (
        <svg className="answer-dot-lines" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polyline points={polyline} />
        </svg>
      )}
      {dots.map((d) => (
        <div key={d.n} className="answer-dot" style={{ left: `${d.x * 100}%`, top: `${d.y * 100}%` }}>
          {d.n}
        </div>
      ))}
    </>
  )
}

/**
 * A visual overlay of the Answer Key on the Part's own crop, for image_select, connect_dots
 * and spot_difference: the raw region/dot keys in `answerLines` are not enough for a human to
 * spot-check these against the crop.
 */
export function AnswerOverlay({
  part,
  cropByImageKey,
}: {
  part: ProblemPart
  cropByImageKey: Map<string, string>
}) {
  if (part.type === 'image_select') {
    const url = cropByImageKey.get(part.image_key)
    if (!url) return null
    return (
      <div className="answer-overlay-wrap">
        <img src={url} alt={`Vùng chọn của phần ${part.part_key}`} />
        <Regions regions={part.regions} selected={new Set(part.answer.selected)} />
      </div>
    )
  }
  if (part.type === 'connect_dots') {
    const url = cropByImageKey.get(part.image_key)
    if (!url) return null
    return (
      <div className="answer-overlay-wrap">
        <img src={url} alt={`Các điểm nối của phần ${part.part_key}`} />
        <Dots dots={part.dots} sequence={part.answer.sequence} />
      </div>
    )
  }
  if (part.type === 'spot_difference') {
    const left = cropByImageKey.get(part.image_left)
    const right = cropByImageKey.get(part.image_right)
    return (
      <div className="answer-overlay-pair">
        {left && (
          <div className="answer-overlay-wrap">
            <img src={left} alt={`Ảnh gốc của phần ${part.part_key}`} />
          </div>
        )}
        {right && (
          <div className="answer-overlay-wrap">
            <img src={right} alt={`Ảnh có điểm khác biệt của phần ${part.part_key}`} />
            <Regions
              regions={part.answer.regions}
              selected={new Set(part.answer.regions.map((r) => r.region_key))}
            />
          </div>
        )}
      </div>
    )
  }
  return null
}
