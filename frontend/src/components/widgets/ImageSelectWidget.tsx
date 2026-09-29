import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type ImageSelectView = Extract<ChildPart, { type: 'image_select' }>

/** `image_select`: tap one region-hotspot on the image (or several, if `multi: true`) --
 * selected, not submitted until ✔ (same "select now, submit on Check" pattern as
 * `multiple_choice`, which `ProblemPlayer.handleToggleOption()` now shares with this type).
 * Regions are laid out from `Region.bbox` (normalised 0-1 on the image). */
export default function ImageSelectWidget({
  part,
  selected,
  onToggleOption,
  slotState,
  disabled,
  imageUrl,
}: WidgetProps<ImageSelectView>) {
  const url = imageUrl(part.image_key)
  // All-or-nothing grading, same as `multiple_choice` -- see that widget's own comment.
  const graded = slotState('__all__')
  const variant = graded === 'correct' ? 'correct' : graded === 'wrong' ? 'wrong' : undefined

  return (
    <div className="widget-image-select" aria-label={part.prompt || 'Chọn vùng đúng'}>
      <div className="widget-image-select-canvas">
        {url && <img src={url} alt="" />}
        {part.regions.map((region) => {
          const [x0, y0, x1, y1] = region.bbox
          const isSelected = selected.includes(region.region_key)
          return (
            <button
              key={region.region_key}
              type="button"
              className={`widget-image-select-region${isSelected ? ' widget-image-select-region-selected' : ''}${isSelected && variant ? ` widget-image-select-region-${variant}` : ''}`}
              style={{
                left: `${x0 * 100}%`,
                top: `${y0 * 100}%`,
                width: `${(x1 - x0) * 100}%`,
                height: `${(y1 - y0) * 100}%`,
              }}
              aria-pressed={isSelected}
              aria-label={`Vùng ${region.region_key}`}
              disabled={disabled}
              onClick={() => onToggleOption(region.region_key)}
            />
          )
        })}
      </div>
    </div>
  )
}
