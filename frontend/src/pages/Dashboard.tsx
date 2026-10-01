import { useState } from "react";
import { Link, Navigate } from "react-router";
import type { DashboardOut } from "../api/client";
import { authRedirect, errorMessage } from "../api/errors";
import {
  useParentDashboard,
  useParentSession,
  useProfiles,
} from "../api/queries";
import ReportProblem from "./review/ReportProblem";
import { statusText, unavailableNote } from "./assignmentUtils";
import "./Dashboard.css";

const BADGE_LABEL: Record<string, string> = {
  week1: "Tuần đầu tiên",
  streak7: "Chuỗi 7 ngày",
  stars100: "100 ngôi sao",
};

const WEEKDAY = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

function percent(ratio: number | null | undefined): string {
  return ratio == null ? "–" : `${Math.round(ratio * 100)}%`;
}

function Bar({ ratio }: { ratio: number | null | undefined }) {
  return (
    <div className="dashboard-bar" aria-hidden="true">
      <span style={{ width: `${Math.round((ratio ?? 0) * 100)}%` }} />
    </div>
  );
}

function shortDate(iso: string): string {
  const [, month, day] = iso.split("-");
  return `${day}/${month}`;
}

function Report({ data }: { data: DashboardOut }) {
  const empty = data.week.sessions === 0;
  return (
    <>
      <section aria-labelledby="dash-overview">
        <h2 id="dash-overview">Tổng quan</h2>
        <ul className="dashboard-stats">
          <li>Sao: {data.stars}</li>
          <li>Chuỗi ngày: {data.streak}</li>
          <li>Bài cần làm lại hôm nay: {data.retry_due_count}</li>
          <li>Bài đang chờ làm lại: {data.retry_open_count}</li>
        </ul>
        <p>
          Huy hiệu:{" "}
          {data.badges.filter((b) => b.earned).length === 0
            ? "chưa có"
            : data.badges
                .filter((b) => b.earned)
                .map((b) => BADGE_LABEL[b.badge_key] ?? b.badge_key)
                .join(", ")}
        </p>
      </section>

      <section aria-labelledby="dash-assignments">
        <h2 id="dash-assignments">Bài được giao</h2>
        {data.assignments.length === 0 && <p>Chưa giao bài nào.</p>}
        <ul className="dashboard-list">
          {data.assignments.map((a) => (
            <li key={a.id} data-testid={`dash-assignment-${a.id}`}>
              {shortDate(a.assigned_date)} · {a.unit_label} {a.lesson_label}:{" "}
              <strong>{statusText(a)}</strong>
              {a.carried_over && " · Hôm qua"}
              {unavailableNote(a) && (
                <p role="alert" className="form-error">
                  {unavailableNote(a)}
                </p>
              )}
            </li>
          ))}
        </ul>
        <p>
          <Link to="/parent/assignments">Giao bài mới</Link>
        </p>
      </section>

      <div className="dashboard-columns">
        <div>
          <section aria-labelledby="dash-week">
            <h2 id="dash-week">
              Tuần này ({shortDate(data.week_start)} –{" "}
              {shortDate(data.week_end)})
            </h2>
            {empty && <p>{data.name} chưa làm bài nào tuần này.</p>}
            <p data-testid="week-totals">
              {data.week.sessions} lượt học · {data.week.minutes} phút · đúng
              ngay lần đầu {percent(data.week.accuracy)}
              {data.week.self_check > 0 &&
                ` · tự kiểm tra ${data.week.self_check} bài`}
            </p>
            <ul className="dashboard-days">
              {data.days.map((d, i) => (
                <li
                  key={d.date}
                  className={
                    d.future
                      ? "dashboard-day dashboard-day-future"
                      : "dashboard-day"
                  }
                  data-testid={`day-${d.date}`}
                >
                  <span>
                    {WEEKDAY[i]} {shortDate(d.date)}
                  </span>
                  <Bar ratio={d.future ? null : d.accuracy} />
                  <span>
                    {d.future
                      ? "–"
                      : `${d.sessions} lượt · ${d.minutes} phút · ${percent(d.accuracy)}`}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="dash-books">
            <h2 id="dash-books">Tiến độ theo sách</h2>
            {data.books.length === 0 && <p>Chưa có bài nào trong sách.</p>}
            <ul className="dashboard-books">
              {data.books.map((b) => (
                <li key={b.book_id}>
                  <strong>{b.title_vi}</strong>: {b.attempted}/{b.total}
                  <Bar ratio={b.total ? b.attempted / b.total : 0} />
                  <ul className="dashboard-list">
                    {b.units.map((u) => (
                      <li key={u.unit_key}>
                        {u.label} {u.title}: {u.attempted}/{u.total}
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          </section>
        </div>

        <div>
          <section aria-labelledby="dash-weak">
            <h2 id="dash-weak">Kiến thức cần luyện thêm (4 tuần qua)</h2>
            {data.weak_concepts.length === 0 && (
              <p>Chưa đủ dữ liệu (cần ít nhất 5 lượt làm cho mỗi kiến thức).</p>
            )}
            <ul className="dashboard-list">
              {data.weak_concepts.map((c) => (
                <li key={c.concept_id}>
                  {c.name_vi}: {percent(c.accuracy)} ({c.first_try_correct}/
                  {c.attempts})
                  <Bar ratio={c.accuracy} />
                </li>
              ))}
            </ul>
          </section>

          <section aria-labelledby="dash-mistakes">
            <h2 id="dash-mistakes">Các bài sai gần đây</h2>
            {data.recent_mistakes.length === 0 && <p>Chưa có bài sai nào.</p>}
            <ul className="dashboard-list">
              {data.recent_mistakes.map((m) => (
                <li
                  key={`${m.problem_id}-${m.completed_at}`}
                  className="dashboard-mistake"
                >
                  <strong>
                    <Link to={`/parent/problems/${m.problem_id}`}>
                      {m.display_label}
                    </Link>
                  </strong>
                  {m.reported && <span> · Đã báo lỗi</span>}
                  {m.parts.map((p) => (
                    <div key={p.part_key}>
                      Bé trả lời: {p.child_answer || "(bỏ trống)"} · Đáp án:{" "}
                      {p.correct_answer}
                    </div>
                  ))}
                  {!m.reported && <ReportProblem problemId={m.problem_id} />}
                </li>
              ))}
            </ul>
          </section>
        </div>
      </div>
    </>
  );
}

/** Story 4.2: the parent's read-only progress dashboard; every figure is computed by the
 * backend (`learning.metrics`), the page only renders it. */
export default function Dashboard() {
  const session = useParentSession();
  const profiles = useProfiles();
  const [chosen, setChosen] = useState("");
  const list = profiles.data ?? [];
  const profileId = chosen || list[0]?.id || "";
  const dashboard = useParentDashboard(profileId);

  if (session.isError) {
    const target = authRedirect(session.error);
    if (target) return <Navigate to={target} replace />;
  }
  if (dashboard.isError) {
    const target = authRedirect(dashboard.error);
    if (target) return <Navigate to={target} replace />;
  }

  return (
    <main className="parent dashboard">
      <h1>Tiến độ của bé</h1>
      <p>
        <Link to="/parent">Về khu vực phụ huynh</Link>
      </p>
      {profiles.isPending && <p>Đang tải…</p>}
      {profiles.isError && (
        <p role="alert" className="form-error">
          {errorMessage(profiles.error)}
        </p>
      )}
      {list.length > 0 && (
        <label>
          Bé{" "}
          <select value={profileId} onChange={(e) => setChosen(e.target.value)}>
            {list.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {dashboard.isPending && profileId !== "" && <p>Đang tải…</p>}
      {dashboard.isError && (
        <>
          <p role="alert" className="form-error">
            {errorMessage(dashboard.error)}
          </p>
          <button type="button" onClick={() => void dashboard.refetch()}>
            Thử lại
          </button>
        </>
      )}
      {dashboard.data && <Report data={dashboard.data} />}
    </main>
  );
}
