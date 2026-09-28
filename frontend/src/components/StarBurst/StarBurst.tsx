import { useMotion } from '../../hooks/useMotion'
import './StarBurst.css'

export interface StarBurstProps {
  count: number
  /** True right when this Star count was just earned: plays the burst animation on mount,
   * unless reduced motion is on (then the static end-state shows immediately). */
  justEarned?: boolean
}

/** An accessible "N ⭐" indicator (gold star, streak flame territory reserved for rewards). */
export default function StarBurst({ count, justEarned = false }: StarBurstProps) {
  const { reduced } = useMotion()
  const bursting = justEarned && !reduced
  return (
    <div className={`star-burst${bursting ? ' star-burst-bursting' : ''}`} role="status">
      <span aria-hidden="true">⭐</span>
      <span className="star-burst-count">{count}</span>
      <span className="sr-only">{`${count} ngôi sao`}</span>
    </div>
  )
}
