import type { BuildRun, CatalogueBook, FullPlan, FullRun } from '../api/client'

export function catalogueBook(overrides: Partial<CatalogueBook> = {}): CatalogueBook {
  return { book_id: 'toan1-2020-q1', title_vi: 'Toán 1 – Quyển 1', page_count: 120, ...overrides }
}

export function buildRun(overrides: Partial<BuildRun> = {}): BuildRun {
  return {
    id: 'run1',
    book_id: 'toan1-2020-q1',
    first_page: 5,
    last_page: 7,
    status: 'running',
    stage: 'extract',
    pages_total: 3,
    pages_done: 1,
    cost_usd: 0.25,
    cost_unknown_count: 0,
    failed_pages: [],
    error: null,
    resumed_from: null,
    started_at: '2026-09-28T00:00:00+00:00',
    updated_at: '2026-09-28T00:00:01+00:00',
    finished_at: null,
    activity: 'Đang trích xuất trang 6/7',
    stale: false,
    run_kind: 'pilot',
    full_id: null,
    max_total_usd: null,
    stop_reason: null,
    unstarted: [],
    ...overrides,
  }
}

export function fullRun(overrides: Partial<FullRun> = {}): FullRun {
  return {
    full_id: 'full1',
    status: 'running',
    max_total_usd: 50,
    spent_usd: 1.5,
    cost_usd: 1.5,
    stop_reason: null,
    unstarted: [],
    books: [
      buildRun({
        id: 'run1',
        run_kind: 'full',
        full_id: 'full1',
        max_total_usd: 50,
        first_page: 1,
        last_page: 70,
        pages_total: 70,
        pages_done: 12,
        cost_usd: 1.5,
        activity: 'Đang trích xuất trang 13/70',
      }),
    ],
    failed_pages: [],
    current_run_id: 'run1',
    ...overrides,
  }
}

export function fullPlan(overrides: Partial<FullPlan> = {}): FullPlan {
  return {
    approved: true,
    books: [
      {
        book_id: 'toan1-2020-q1',
        title_vi: 'Toán 1 – Quyển 1',
        grade: 1,
        pages_in_scope: 70,
        pages_to_call: 60,
        pages_to_verify: 60,
        probe: false,
        skipped: null,
      },
      {
        book_id: 'toan3-2020-q1',
        title_vi: 'Toán 3 – Quyển 1',
        grade: 3,
        pages_in_scope: 30,
        pages_to_call: 30,
        pages_to_verify: 30,
        probe: true,
        skipped: null,
      },
    ],
    pages_to_call: 90,
    estimate_usd: 12.5,
    worst_case_usd: 180,
    gate_est_cost: 400,
    ...overrides,
  }
}
