import type { BuildRun, CatalogueBook } from '../api/client'

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
    ...overrides,
  }
}
