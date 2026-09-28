import type { GateReport, SpotCheckItem, SpotCheckOut } from '../api/client'
import { PROBLEM_ID } from './reviewFixtures'

export function spotItem(overrides: Partial<SpotCheckItem> = {}): SpotCheckItem {
  return {
    problem_id: PROBLEM_ID,
    position: 1,
    problem_type: 'number_input',
    display_label: 'Bài 1',
    verdict: null,
    note: '',
    checked_at: null,
    verdict_hash: null,
    first_wrong_at: null,
    counted: null,
    content_hash: 'h1',
    stale: false,
    retired: false,
    ...overrides,
  }
}

export function spotCheck(items: SpotCheckItem[], overrides: Partial<SpotCheckOut> = {}): SpotCheckOut {
  const counted = items.filter((i) => i.verdict !== null && !i.stale)
  const correct = counted.filter((i) => i.verdict === 'correct').length
  return {
    sample_id: 's1',
    seed: 42,
    created_at: '2026-09-27T00:00:00+00:00',
    size: items.length,
    correct,
    wrong: counted.length - correct,
    stale: items.filter((i) => i.stale).length,
    checked: counted.length,
    items,
    ...overrides,
  }
}

type GateOverrides = Partial<Omit<GateReport, 'fallback' | 'accuracy' | 'cost'>> & {
  fallback?: Partial<GateReport['fallback']>
  accuracy?: Partial<GateReport['accuracy']>
  cost?: Partial<GateReport['cost']>
}

/** A pilot that passes both checks: 40 Problems, 30/30 Đúng, $3.20 over 16 pages. */
export function gateReport(overrides: GateOverrides = {}): GateReport {
  const { fallback, accuracy, cost, ...rest } = overrides
  return {
    has_pilot: true,
    pilot_pages: 16,
    pilot_problems: 40,
    books: [{ book_id: 'toan1-2020-q1', pilot_pages: 16 }],
    thresholds: { max_fallback_share: 0.15, min_key_accuracy: 0.98, min_sample: 30 },
    fallback: {
      passed: true,
      value: 0.05,
      threshold: 0.15,
      problems: 40,
      with_fallback: 2,
      ...fallback,
    },
    accuracy: {
      passed: true,
      value: 1,
      threshold: 0.98,
      correct: 30,
      wrong: 0,
      stale: 0,
      unchecked: 0,
      sample_id: 's1',
      sample_size: 30,
      min_sample: 30,
      enough_sample: true,
      sample_outdated: false,
      eligible_problems: 40,
      enough_problems: true,
      ...accuracy,
    },
    cost: {
      pilot_cost: 3.2,
      reported_cost: 3.2,
      unknown_cost_calls: 0,
      unknown_cost_cap_usd: 1,
      per_page: 0.2,
      pilot_pages: 16,
      total_pages: 2140,
      remaining_pages: 2124,
      est_cost: 424.8,
      ...cost,
    },
    checks_passed: true,
    approval: null,
    approved: false,
    ...rest,
  }
}
