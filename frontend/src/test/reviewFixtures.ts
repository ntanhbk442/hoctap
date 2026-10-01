import type { ProblemDetail, ProblemDoc, ProblemSummary } from '../api/client'

export const PROBLEM_ID = 'toan1-2020-q1.tuan-5.tiet-2.bai-1'

export function summary(overrides: Partial<ProblemSummary> = {}): ProblemSummary {
  return {
    problem_id: PROBLEM_ID,
    book_id: 'toan1-2020-q1',
    unit_key: 'tuan-5',
    lesson_key: 'tiet-2',
    position: 12000,
    display_label: 'Bài 1',
    instruction: 'Tính:',
    awaiting_approval: false,
    conflict: false,
    report: false,
    hidden: false,
    duplicate: false,
    approved: false,
    visible: true,
    retired: false,
    no_concepts: false,
    ...overrides,
  }
}

export function doc(answer = '5'): ProblemDoc {
  return {
    schema_version: 'v1',
    problem_id: PROBLEM_ID,
    book_id: 'toan1-2020-q1',
    unit_key: 'tuan-5',
    lesson_key: 'tiet-2',
    problem_label: 'bai-1',
    display_label: 'Bài 1',
    instruction: 'Tính:',
    layout: 'sequence',
    source_pages: [{ page: 12, bbox: [0.08, 0.1, 0.92, 0.35] }],
    images: [],
    concept_ids: [],
    concept_proposals: [],
    parts: [
      {
        part_key: 'a',
        type: 'number_input',
        prompt: '',
        image_keys: [],
        template: '3 + 2 = [[s1]]',
        slots: [{ slot_key: 's1' }],
        answer: [{ key: 's1', value: answer }],
        hint: 'Con đếm thêm 2 bắt đầu từ 3 nhé.',
        solution: { steps: ['Bắt đầu từ 3, đếm thêm 2: bốn, năm.'], final: '3 + 2 = 5' },
      },
    ],
  }
}

export function detail(overrides: Partial<ProblemDetail> = {}): ProblemDetail {
  const d = doc()
  return {
    summary: summary({ awaiting_approval: true, visible: false }),
    extracted: d as unknown as ProblemDetail['extracted'],
    effective: d,
    effective_error: [],
    content_hash: 'h1',
    overrides: [],
    conflicts: [],
    status: {
      needs_review: true,
      verify_status: 'disagree',
      approved_hash: null,
      approved: false,
      hidden: false,
      duplicate: false,
      retired: false,
      visible: false,
    },
    reports: [],
    crop_urls: [`/assets-data/crops/toan1-2020-q1/${PROBLEM_ID}/_problem.jpg`],
    page_urls: ['/assets-data/pages/toan1-2020-q1/p012.jpg'],
    ...overrides,
  }
}
