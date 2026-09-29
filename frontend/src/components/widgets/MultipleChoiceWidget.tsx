import ChoiceChip from '../ChoiceChip/ChoiceChip'
import type { ChildPart, WidgetProps } from './types'
import './widgets.css'

type MultipleChoiceView = Extract<ChildPart, { type: 'multiple_choice' }>

/** `multiple_choice`: one `ChoiceChip` per option; tap selects (not submitted until ✔),
 * respecting `multi` (multi-select) vs single-select (Boundaries & Constraints). */
export default function MultipleChoiceWidget({
  part,
  selected,
  onToggleOption,
  slotState,
  disabled,
  imageUrl,
}: WidgetProps<MultipleChoiceView>) {
  // All-or-nothing grading (`_grade_set()`) has no per-option wrong key -- once graded, every
  // option shares the same verdict rather than singling one out as "the wrong one".
  const graded = slotState('__all__')
  const variant = graded === 'correct' ? 'correct' : graded === 'wrong' ? 'wrong' : undefined

  return (
    <div className="widget-multiple-choice" role="group" aria-label={part.prompt || 'Chọn đáp án'}>
      {part.options.map((option) => {
        const isSelected = selected.includes(option.option_key)
        const url = option.image_key ? imageUrl(option.image_key) : undefined
        return (
          <ChoiceChip
            key={option.option_key}
            selected={isSelected}
            variant={isSelected ? variant : undefined}
            ariaLabel={option.text ?? undefined}
            onClick={disabled ? undefined : () => onToggleOption(option.option_key)}
          >
            {option.text ?? (url ? <img src={url} alt="" /> : option.option_key)}
          </ChoiceChip>
        )
      })}
    </div>
  )
}
