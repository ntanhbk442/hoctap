import SpeakerButton from '../SpeakerButton/SpeakerButton'
import './HintBubble.css'

export interface HintBubbleProps {
  text: string
  speaking?: boolean
  onSpeak?: () => void
}

/** Soft purple bubble with 💡, the Hint text (`body` typography) and a 🔊 slot
 * (`hint-bubble` spec). Appears after the first wrong Attempt, or on 💡 tap. */
export default function HintBubble({ text, speaking = false, onSpeak }: HintBubbleProps) {
  return (
    <div className="hint-bubble" role="note">
      <span className="hint-bubble-icon" aria-hidden="true">
        💡
      </span>
      <p className="hint-bubble-text">{text}</p>
      <SpeakerButton label={`Nghe gợi ý: ${text}`} playing={speaking} onClick={onSpeak} />
    </div>
  )
}
