import ZoomableImage from '../ZoomableImage/ZoomableImage'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type FallbackView = Extract<ChildPart, { type: 'fallback' }>

/** A `fallback` Problem's own crop -- no machine-gradable answer at all (FR-11), so this
 * widget shows only the printed page crop, pinch-zoomable via `ZoomableImage` (Boundaries
 * & Constraints). `ProblemPlayer`'s dedicated `FallbackPartPlayer` (not this generic
 * `WidgetProps`-shared switcher) owns the "Xem đáp án" reveal / self-mark flow around it,
 * since that flow has no ✔ Kiểm tra/NumberPad/Attempt at all -- fundamentally not the
 * shared answer-widget shape every other Part type here uses. */
export default function FallbackWidget({ part, imageUrl }: Pick<WidgetProps<FallbackView>, 'part' | 'imageUrl'>) {
  const url = imageUrl(part.image_key)
  return (
    <div className="widget-fallback">
      {url ? <ZoomableImage src={url} alt={part.prompt || 'Hình bài tập'} /> : null}
    </div>
  )
}
