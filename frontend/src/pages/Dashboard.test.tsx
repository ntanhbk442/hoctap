import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DashboardOut } from "../api/client";
import { mockApi, renderAt } from "../test/render";
import Dashboard from "./Dashboard";

afterEach(() => {
  vi.unstubAllGlobals();
});

const PROFILES = [
  { id: "p1", name: "Bin", avatar: "cat", grade: 1, auto_play: true },
  { id: "p2", name: "Na", avatar: "cat", grade: 1, auto_play: true },
];

const DATES = [
  "2026-09-28",
  "2026-09-29",
  "2026-09-30",
  "2026-10-01",
  "2026-10-02",
  "2026-10-03",
  "2026-10-04",
];

function dashboard(over: Partial<DashboardOut> = {}): DashboardOut {
  return {
    profile_id: "p1",
    name: "Bin",
    grade: 1,
    week_start: "2026-09-28",
    week_end: "2026-10-04",
    stars: 12,
    streak: 3,
    badges: [
      { badge_key: "week1", earned: true, earned_at: "x" },
      { badge_key: "streak7", earned: false, earned_at: null },
      { badge_key: "stars100", earned: false, earned_at: null },
    ],
    retry_due_count: 2,
    retry_open_count: 4,
    days: DATES.map((date, i) => ({
      date,
      future: i > 2,
      sessions: i === 1 ? 2 : 0,
      minutes: i === 1 ? 9 : 0,
      first_try_correct: i === 1 ? 3 : 0,
      problems: i === 1 ? 4 : 0,
      self_check: 0,
      accuracy: i === 1 ? 0.75 : null,
    })),
    week: {
      sessions: 2,
      minutes: 9,
      first_try_correct: 3,
      problems: 4,
      self_check: 0,
      accuracy: 0.75,
    },
    books: [
      {
        book_id: "b",
        title_vi: "Toán 1",
        attempted: 3,
        total: 10,
        units: [
          {
            unit_key: "u",
            label: "TUẦN 5",
            title: "",
            attempted: 3,
            total: 10,
          },
        ],
      },
    ],
    weak_concepts: [
      {
        concept_id: "g1.x",
        name_vi: "Cộng trong phạm vi 10",
        attempts: 5,
        first_try_correct: 1,
        accuracy: 0.2,
      },
    ],
    recent_mistakes: [
      {
        problem_id: "pr",
        display_label: "Bài 2",
        completed_at: "x",
        parts: [{ part_key: "a", child_answer: "9", correct_answer: "5" }],
        reported: false,
      },
    ],
    assignments: [],
    ...over,
  };
}

const session = {
  "GET /api/v1/parent/session": { status: 200, body: { authenticated: true } },
};

describe("Dashboard", () => {
  it("renders every section from the API data", async () => {
    mockApi({
      ...session,
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": { status: 200, body: dashboard() },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(await screen.findByText("Sao: 12")).toBeInTheDocument();
    expect(screen.getByText("Chuỗi ngày: 3")).toBeInTheDocument();
    expect(screen.getByText(/Tuần đầu tiên/)).toBeInTheDocument();
    expect(screen.getByTestId("week-totals")).toHaveTextContent(
      "2 lượt học · 9 phút · đúng ngay lần đầu 75%",
    );
    expect(
      within(screen.getByTestId("day-2026-09-29")).getByText(
        "2 lượt · 9 phút · 75%",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("day-2026-10-02")).getByText("–"),
    ).toBeInTheDocument();
    expect(screen.getByText("Toán 1").closest("li")).toHaveTextContent("3/10");
    expect(screen.getByText(/Cộng trong phạm vi 10/)).toHaveTextContent("20%");
    expect(screen.getByText(/Bé trả lời: 9 · Đáp án: 5/)).toBeInTheDocument();
  });

  it("lists Assignment statuses with the chunk of a started one", async () => {
    const base = {
      profile_id: "p1",
      book_id: "b",
      unit_key: "u",
      lesson_key: "l",
      book_title_vi: "Toán 1",
      unit_label: "TUẦN 5",
      lesson_label: "Tiết 2",
      lesson_title: "",
      resolvable: true,
    };
    mockApi({
      ...session,
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": {
        status: 200,
        body: dashboard({
          assignments: [
            { ...base, id: "a1", assigned_date: "2026-10-01", status: "todo", carried_over: false },
            {
              ...base,
              id: "a2",
              assigned_date: "2026-09-29",
              status: "doing",
              part: 2,
              part_count: 2,
              carried_over: true,
            },
            { ...base, id: "a3", assigned_date: "2026-09-28", status: "done", carried_over: false },
          ],
        }),
      },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(await screen.findByTestId("dash-assignment-a1")).toHaveTextContent("Chưa làm");
    expect(screen.getByTestId("dash-assignment-a2")).toHaveTextContent("Đang làm (Phần 2/2)");
    expect(screen.getByTestId("dash-assignment-a2")).toHaveTextContent("Hôm qua");
    expect(screen.getByTestId("dash-assignment-a3")).toHaveTextContent("Đã xong");
  });

  it("flags an Assignment whose Lesson no longer resolves any visible Problem", async () => {
    // Orchestrator's Independent Audit (spec-4-3 #1, 2026-10-01): the Dashboard must
    // surface a `resolvable: false` row so Anh can see it needs attention, instead of it
    // looking identical to an ordinary not-yet-started Assignment.
    mockApi({
      ...session,
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": {
        status: 200,
        body: dashboard({
          assignments: [
            {
              id: "a1",
              profile_id: "p1",
              book_id: "b",
              unit_key: "u",
              lesson_key: "l",
              book_title_vi: "Toán 1",
              unit_label: "TUẦN 5",
              lesson_label: "Tiết 2",
              lesson_title: "",
              assigned_date: "2026-10-01",
              status: "todo",
              carried_over: false,
              resolvable: false,
            },
          ],
        }),
      },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(await screen.findByTestId("dash-assignment-a1")).toHaveTextContent(
      "Không có bài nào hiển thị cho bé",
    );
  });

  it("shows friendly empty states for a new child", async () => {
    mockApi({
      ...session,
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": {
        status: 200,
        body: dashboard({
          stars: 0,
          streak: 0,
          badges: [],
          days: dashboard().days.map((d) => ({
            ...d,
            sessions: 0,
            minutes: 0,
            accuracy: null,
          })),
          week: {
            sessions: 0,
            minutes: 0,
            first_try_correct: 0,
            problems: 0,
            self_check: 0,
            accuracy: null,
          },
          books: [],
          weak_concepts: [],
          recent_mistakes: [],
        }),
      },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(
      await screen.findByText("Bin chưa làm bài nào tuần này."),
    ).toBeInTheDocument();
    expect(screen.getByText("Chưa có bài sai nào.")).toBeInTheDocument();
    expect(screen.getByText(/Chưa đủ dữ liệu/)).toBeInTheDocument();
  });

  it("switches child and shows only that child", async () => {
    mockApi({
      ...session,
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": { status: 200, body: dashboard() },
      "GET /api/v1/parent/dashboard/p2": {
        status: 200,
        body: dashboard({ profile_id: "p2", name: "Na", stars: 99 }),
      },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(await screen.findByText("Sao: 12")).toBeInTheDocument();
    fireEvent.change(await screen.findByRole("combobox"), {
      target: { value: "p2" },
    });
    expect(await screen.findByText("Sao: 99")).toBeInTheDocument();
    expect(screen.queryByText("Sao: 12")).not.toBeInTheDocument();
  });

  it("redirects to login when the session expired", async () => {
    mockApi({
      "GET /api/v1/parent/session": {
        status: 401,
        body: { error: { code: "UNAUTHORIZED", message: "Cần nhập mã PIN." } },
      },
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": {
        status: 401,
        body: { error: { code: "UNAUTHORIZED", message: "Cần nhập mã PIN." } },
      },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(await screen.findByText("login screen")).toBeInTheDocument();
  });

  it("links a mistake to the preview and offers Báo lỗi; a reported row shows its state", async () => {
    mockApi({
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": {
        status: 200,
        body: dashboard(),
      },
      "POST /api/v1/parent/review/problems/pr/reports": {
        status: 200,
        body: {
          id: "r",
          problem_id: "pr",
          kind: "parent",
          note: "",
          status: "open",
          created_at: "x",
          resolved_at: null,
        },
      },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    const link = await screen.findByRole("link", { name: "Bài 2" });
    expect(link).toHaveAttribute("href", "/parent/problems/pr");
    fireEvent.click(screen.getByRole("button", { name: "Báo lỗi" }));
    expect(await screen.findByText(/Đã báo lỗi\./)).toBeInTheDocument();
  });

  it("marks a reported mistake and hides its button", async () => {
    const d = dashboard();
    d.recent_mistakes[0].reported = true;
    mockApi({
      "GET /api/v1/profiles": { status: 200, body: PROFILES },
      "GET /api/v1/parent/dashboard/p1": { status: 200, body: d },
    });
    renderAt("/parent/dashboard", <Dashboard />);
    expect(await screen.findByText(/· Đã báo lỗi/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Báo lỗi" })).not.toBeInTheDocument();
  });
});
