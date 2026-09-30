import type { WorksheetRef } from '../api/client'

/** The `/parent/print` link of a Lesson (an Assignment is its Lesson) or a Concept. */
export function printLink(ref: WorksheetRef): string {
  const params = new URLSearchParams(
    'conceptId' in ref
      ? { concept_id: ref.conceptId, profile_id: ref.profileId }
      : { book_id: ref.bookId, unit_key: ref.unitKey, lesson_key: ref.lessonKey },
  )
  return `/parent/print?${params.toString()}`
}
