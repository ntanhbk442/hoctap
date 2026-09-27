---
name: Học Tập
status: final
created: 2026-09-26
updated: 2026-09-26
sources:
  - ../../prds/prd-hoctap-2026-09-26/prd.md
  - ../../briefs/brief-hoctap-2026-09-26/brief.md
---

# Học Tập — Experience Spine

## Foundation

- **Form factor:** a web app installed as a PWA, served from the home PC over the home LAN (PRD NFR-2).
  - **Primary surface:** a tablet, used by the child in portrait or landscape.
  - **Secondary surface:** the PC browser, used by the parent for the Parent Area and printing.
- **No UI system is named.** Everything is custom-built on the `DESIGN.md` tokens, which are the visual reference.
- **Two modes with a hard boundary:**
  - **Child mode** is the default and is audio-first, with almost no text.
  - The **Parent Area** is behind a PIN, text-first and denser.
- All Glossary terms (Problem, Part, Session, Star, Retry Queue…) are used exactly as defined in PRD §3.

## Information Architecture

| Surface | Mode | Reached from | Purpose | PRD |
|---|---|---|---|---|
| Profile picker | Child | App open, when there is more than 1 Child Profile | Tap your avatar. Skipped when there is only 1 profile. | FR-18 |
| Home | Child | App open or profile picker | Today's Assignment, Luyện lại (practise again), Tiếp tục (continue), Streak, Stars and the latest 3 badges | FR-8, FR-16 |
| Huy hiệu của em (your badges) | Child | Tapping the badges on Home | Every badge, earned ones in colour and locked ones in grey with 🔊 saying how to earn them | FR-16 |
| Library | Child | Home, "📚 Sách" (books) | Grade → Book → Unit → Lesson, with a Concept tab | FR-7 |
| Problem | Child | Starting a Session | Plays one Problem at a time | FR-9 – FR-13 |
| Session summary | Child | Last Problem of a Session | Stars, number correct on the first try, Streak, any new badge, "Luyện lại bài sai" | FR-14, FR-16 |
| Quiz results | Child | Last Problem of a quiz Session (FR-23) | Every Problem marked ✔ or ↻, with a Solution for each wrong one, then Stars | FR-23 |
| Concept Guide | Child | 📖 on the Problem, or the Library Concept tab | Explanation, worked example, "Luyện tập" (practise) | FR-15 |
| PIN gate | Parent | 🔒 at the bottom corner of Home (long-press 2 seconds) | Enter the 4-digit PIN | FR-18 |
| First-run setup | Parent | First app open, when there are no Child Profiles | Create the PIN, then the first Child Profile (name, avatar, Grade) | FR-18 |
| Dashboard | Parent | PIN gate | Per child: Sessions and time per day and week, first-try accuracy, progress per Book and Unit, weakest Concepts (at least 5 Attempts), recent mistakes, Assignment status | FR-19, FR-20 |
| Parent Library | Parent | Parent menu | The same tree as the child Library, plus "Giao bài" (assign), "In phiếu" (print) and "Xem" (preview) on every Lesson and Concept | FR-7, FR-20, FR-22 |
| Assign | Parent | Dashboard, or any Lesson or Concept in the Parent Library | Pick a Problem Set and a date | FR-20 |
| Content Review | Parent | Dashboard, "Duyệt nội dung" (review content) | Tabs: **Cần duyệt** (to review: `needs_review` and Error Reports), **Tất cả** (all: browse every Problem by Book), **Kiểm tra ngẫu nhiên** (spot-check: random sample for the FR-5 and SM-3 accuracy check) and **Khái niệm** (Concepts: edit the Concept list per Grade). Each Problem opens an editor beside its source page, with Duyệt (approve), Ẩn (hide) and Đáp án đúng/sai (answer right/wrong) | FR-4, FR-5, FR-6, FR-21 |
| Extraction | Parent (PC) | Parent menu | Pilot and full run, progress, go/no-go report | FR-1 – FR-5 |
| Print | Parent (PC) | Any Problem Set, "In phiếu" (print worksheet) | Print preview: A4 worksheet plus an answer page | FR-22 |
| Settings | Parent | Parent menu | Child Profiles, PIN, auto-play audio per child, "Sao lưu" (backup: download one file) and "Khôi phục" (restore: upload the file, confirm, then replace) | FR-18, FR-10, NFR-7 |

Child-mode navigation is flat. Every child surface has one big ⬅ back button in the top-left corner and nothing else in the chrome. There are no tabs, no drawer and no menus. [ASSUMPTION] The 🔒 long-press means a child can't open the Parent Area by accident.

## Voice and Tone

The child is addressed as **"em"**, like the Archimedes books. Every child-facing string is short, warm and spoken. The Parent Area is neutral and factual.

| Moment | Say (child) | Don't |
|---|---|---|
| Correct | "Đúng rồi! Giỏi quá!" (Correct! Great job!) (the praise line rotates, about 6 variants) | "Chính xác 100%" (100% accurate) |
| First wrong answer | "Chưa đúng, em thử lại nhé!" (Not yet, try again!), then the Hint plays | "Sai rồi!" (Wrong!), "Không đúng" (Incorrect) |
| Second wrong answer | "Mình cùng xem cách làm nhé." (Let's look at how to do it together.) | "Đáp án là…" (The answer is…) with no explanation |
| Session end | "Em đã hoàn thành bài! Em được 22 ngôi sao." (You finished the lesson! You got 22 stars.) | Percentages or grades |
| Streak | "4 ngày liên tiếp! 🔥" (4 days in a row!) | "Đừng làm mất chuỗi!" (Don't lose your streak!) (no loss framing) |
| Empty Retry Queue | The "Luyện lại" card is not shown | "Không có bài nào" (There are no problems) |

**Parent voice:** plain labels, for example "Độ chính xác lần đầu: 81%" (first-try accuracy: 81%) or "Khái niệm yếu nhất" (weakest concept). Numbers come first, with no exclamation marks.

## Audio Behaviour

The child can't read yet, so audio is the most important channel.

- **Auto-play:** the instruction plays when a Problem opens. The parent can switch this off per Child Profile (FR-10).
- **Every piece of text has a 🔊 button:** instructions, Parts, answer options, Hints, Solutions, Home card labels and Concept Guides.
- **One voice at a time:** starting a new clip stops the one playing. Leaving a screen stops audio.
- **Replay:** the child can tap 🔊 again at any time. Replaying never costs Stars.
- **Feedback sounds:** a short chime for correct, a soft "boop" for not yet, and a fanfare at Session end. These are separate from speech and never stop a Hint from being heard: the feedback sound plays first, then the Hint speech starts after about 400 ms.
- **No audio:** if a clip is missing, the 🔊 button is greyed out and the text stays visible. Nothing is blocked.

## Component Patterns

Behavioural rules only. The visual specs are in `DESIGN.md` Components.

| Component | Behavioural rules |
|---|---|
| Home card | Tapping it starts or opens its target. A long press plays its 🔊 label, so a child can "ask" what a card is without opening it. |
| Answer slot | Tapping a slot makes it active. Digits from the number pad go into the active slot, and ⌫ deletes. The next empty slot becomes active automatically. |
| Number pad | Shown only when the Problem has number slots. It is never the system keyboard. |
| ✔ Kiểm tra | Enabled only when every slot of the current Part is filled. It grades the Part (FR-12). |
| Feedback banner | In quiz mode, ✔ only records the answer ("Đã lưu", saved) with no right or wrong shown. Otherwise, on a correct answer "Tiếp ➜" (next) advances; on a wrong answer the banner closes by itself after the Hint audio and keeps the child's answer so they can edit it. |
| Hint bubble | Not available in quiz mode (FR-23). Otherwise it appears after the first wrong Attempt, or when the child taps 💡 before answering. The child's Stars are then capped (FR-16). |
| Solution panel | Appears after the second wrong Attempt and reveals the steps one at a time with audio, then shows "Tiếp ➜". |
| 📖 Concept button | Opens the Concept Guide as an overlay. Closing it returns to the same Problem with the child's answer kept. |
| 🚩 flag (child) | In the top bar of the Problem screen. It asks "Báo cho bố mẹ bài này có lỗi?" (tell your parents this problem has a mistake?) with Có (yes) or Không (no), and sends an Error Report (FR-21). |
| 🚩 "Báo lỗi" (parent) | On every Problem in the Parent Library preview ("Xem") and in the recent-mistakes list on the Dashboard. It asks for an optional note, creates an Error Report, and **hides** the Problem from the child until it is resolved in Content Review (FR-21). |

### Problem Type interactions (FR-9)

| Type | Interaction |
|---|---|
| `number_input` | Tap a slot, then type on the number pad. |
| `compare` | Three large chips `<` `=` `>` between the two expressions. Tapping one fills the slot. |
| `multiple_choice` / `image_select` | Tap one chip or image. It is selected, but not submitted until ✔. |
| `order` | Drag number tiles into a row of slots, where they snap into place. Tapping a tile then a slot also works, for children who find dragging hard. |
| `number_tree` | The tree diagram has tappable empty nodes. Each node works like `number_input`. |
| `grid_fill` | Tap a cell, then use the number pad. Cells given in the book are locked (grey). |
| `match` | Tap an item on the left, then an item on the right, and a line is drawn. Tapping a line removes it. |
| `count_image` | The image is shown with the number pad. Tapping an object in the image puts a small dot on it, to help counting (not graded). |
| `dot_draw` | Tapping inside the box adds a dot; tapping a dot removes it. A counter shows how many there are. |
| `connect_dots` | Tap the numbered dots in order. A line follows. A wrong next dot wiggles, and does not count as an Attempt until ✔. |
| `spot_difference` | Tap each difference on the right-hand image (the left-hand image is the reference). A correct spot gets a ring; a counter shows "2/5". |
| `expression_input` | A number pad with + − × : ( ) =. |
| `fallback` | The page crop can be pinch-zoomed. "Xem đáp án" (see answer) reveals the Solution, then "Em làm đúng" / "Em chưa đúng" (I got it right / not yet) (FR-11). |

## State Patterns

| State | Surface | Treatment |
|---|---|---|
| First launch, no profile | Tablet or PC | Opens First-run setup: the PIN, then the first Child Profile. |
| First launch, no content | Home (child) | "Chưa có bài học. Nhờ bố mẹ tải sách nhé!" (No lessons yet. Ask your parents to load the books!) with a 🔊 button. |
| No Assignment today | Home | The "Bài hôm nay" card becomes "Học tiếp" (keep learning), which opens the next unfinished Lesson in the child's Grade, in Book order. This is the UX's way of meeting "Tiếp tục" in FR-8 when there's no Assignment. [ASSUMPTION] |
| Assignment carried over | Home | Same card, with a small "Hôm qua" (yesterday) ribbon. No guilt copy. |
| Correct | Problem | The slot turns green, a chime plays, the banner shows and Stars fly to the counter. |
| First wrong | Problem | The slot shakes (reduced motion: no shake) and turns orange, then the Hint bubble and its audio play. |
| Second wrong | Problem | The Solution panel opens. The Problem is already in the Retry Queue. |
| Problem hidden (`needs_review`, flagged by the parent, or hidden in Content Review) | Library / Session | Skipped silently in child mode. The progress count excludes it. A child's 🚩 does **not** hide the Problem (FR-21): the child sees "Đã báo cho bố mẹ" (your parents have been told) and carries on. |
| Lesson longer than 10 Problems | Library / Home / Problem | Split into Sessions of at most 10 (FR-8). The Library shows the Lesson as "Phần 1/2", "Phần 2/2" (part 1 of 2…). Progress dots cover only the current Session. The Assignment card says "Phần 2/2" until every part is done, and only then is the Assignment done. |
| Quiz Session (Phiếu tự luyện cuối tuần) | Library / Problem | The Lesson card shows 📝 "Kiểm tra" (quiz). There's no 💡 button, no Hint and no right-or-wrong feedback during play; the progress dots only fill. Quiz results appear at the end (FR-23). |
| Retry Queue has Problems due | Home | The "Luyện lại" card appears only when at least one queued Problem is due, meaning its last wrong Attempt was on an earlier calendar day (FR-17). |
| "Luyện lại bài sai" on the summary | Session summary | Replays that Session's wrong Problems straight away, as extra practice. These Attempts earn no Stars and don't count towards leaving the Retry Queue, so the next-day rule in FR-17 still applies. [ASSUMPTION] |
| New badge earned | Session summary | The badge pops in with a fanfare and 🔊 reads its name. |
| Server unreachable (tablet off the home Wi-Fi) | Any child screen | A full-screen friendly message: "Máy tính bảng chưa kết nối với máy tính ở nhà." (The tablet isn't connected to the computer at home.) with a 🔊 button and a retry. Progress for the current Problem is kept locally and synced when the connection returns. [ASSUMPTION] |
| Session interrupted (tablet closed) | Home | A "Tiếp tục" (continue) card resumes at the same Problem (NFR-7). |
| Extraction running | Parent: Extraction | A progress bar by Book and page, cost so far, a failed-pages list and Pause/Resume. |
| Pilot finished | Parent: Extraction | A go/no-go report with three checks (fallback ≤ 15%, answers ≥ 98%, cost). "Chạy toàn bộ" (run everything) is enabled only after Anh confirms. |
| Empty review list | Parent: Content Review | "Không có bài cần duyệt." (No problems need review.) |
| Assignment status | Parent: Dashboard | One of: **Chưa làm** (not started), **Đang làm** (in progress, for example "Phần 1/2"), **Đã xong** (done), or **Chuyển sang hôm nay** (carried over to today). |

## Interaction Primitives

- **Tap first.** Drag is used only for `order`, and even there a tap works too.
- **No swipe navigation, and no gestures** beyond pinch-zoom on `fallback` crops.
- **No timers on child screens.** Nothing counts down, and the child is never rushed.
- **Long press** is used for only two things: speaking a Home card's label, and the 🔒 Parent Area entry.
- **Banned in child mode:** hearts or lives, leaderboards, ads, external links, push notifications, and pop-ups the child didn't ask for.

## Accessibility Floor

Behaviour only. Colour contrast is covered in `DESIGN.md`.

- Every control has an accessible name, and the instruction text is always present in the DOM for screen readers, alongside the audio.
- Touch targets are at least `{spacing.touch-min}` (64px), and number-pad keys are `{spacing.key}` (80px).
- Reduce Motion: no shake, no flying stars, and no confetti. The static state change and the sounds remain.
- No state is shown by colour alone: ✔, ↻ and 💡 icons always go with it.
- On the PC, the whole Parent Area can be used with the keyboard. Child mode also works with a keyboard: the number keys type into slots.

## Responsive & Platform

| Surface | Layout |
|---|---|
| Tablet portrait | The work area is on top, and the action bar with the number pad and ✔ is along the bottom. |
| Tablet landscape | The work area is on the left (60%), and the action bar with the number pad and ✔ is on the right (40%). |
| PC browser | Child mode is centred, with a maximum width of 1024px. The Parent Area uses a two-column dashboard. |
| Print | Print CSS: A4, black-and-white-safe, answer slots as empty boxes, and the answer page after a page break (FR-22). |

The PWA can be installed on the tablet's home screen, full screen, with no browser chrome.

## Inspiration & Anti-patterns

- **From Khan Academy Kids:** everything can be read aloud, there is no reading barrier, and it's calm and warm.
- **From Duolingo:** the satisfying "chunky" check button, the correct/incorrect banner sliding up from the bottom, streaks, and progress dots.
- **Rejected from Duolingo:** hearts and lives, fear of losing a streak, and pushy notifications. A 6-year-old shouldn't feel punished for being wrong or for missing a day.
- **Rejected:** a mascot (Anh's choice). Warmth comes from colour, sound and celebration instead.

## Key Flows

### Flow 1 — Tonight's lesson (Bin, 6, after dinner, family tablet) · UJ-1
1. Bin taps the app icon. There's one profile, so Home opens directly.
2. Bin taps the big "Bài hôm nay: Tuần 3 – Tiết 2" card (long-pressing it first to hear it).
3. Problem 1 opens, and the instruction plays automatically.
4. Bin taps the slot, types 4 and taps ✔ Kiểm tra. The chime plays, "Đúng rồi!" appears, and 3 Stars fly up. Bin taps "Tiếp ➜".
5. Problem 4 is a `number_tree`. Bin enters a wrong answer: the node turns orange and a "boop" plays, then the Hint bubble appears and its audio says: "Hai số ở dưới cộng lại bằng số ở trên" (the two numbers below add up to the number on top).
6. Bin edits the node, and it's correct: 1 Star.
7. **Climax:** after Problem 8, the summary fanfare plays: "Em đã hoàn thành bài! Em được 22 ngôi sao", 7 of 8 correct on the first try, and the flame grows to 4 days. Bin runs to show Anh.

**Failure:** if the tablet is off the home Wi-Fi, the friendly "not connected" screen appears with its 🔊 button, and nothing is lost.

### Flow 2 — Checking and assigning (Anh, the PC, later that evening) · UJ-2
1. Anh opens the PC browser (or long-presses 🔒 on Home) and enters the PIN.
2. The Dashboard shows: 5 Sessions, 42 Problems, 81% first-try accuracy, weakest Concept "So sánh số" at 55%.
3. Anh opens "Lỗi gần đây" (recent mistakes) and sees Bin's `>` answers next to the correct `<`.
4. Anh taps "Giao bài" (assign) on "So sánh số", picks the 2024–25 Book's set and tomorrow's date, and taps Lưu (save).
5. **Climax:** tomorrow's card appears in the Dashboard's Assignments list with the status "Chưa làm" (not started). Tomorrow Bin will see it first.

**Edge:** Anh spots a wrong answer in the recent-mistakes list, taps the parent 🚩 "Báo lỗi", and the Problem is hidden and appears in Content Review.

### Flow 3 — Weekend worksheet (Anh, PC) · UJ-3
1. Anh opens Tuần 4 in the Parent Library and taps "In phiếu".
2. **Climax:** the print preview shows a clean A4 worksheet with an answer page. Anh prints it or saves it as a PDF.

### Flow 4 — Loading the books (Anh, PC, once) · UJ-4
1. Parent menu → Extraction → "Chạy thử (pilot)" (trial run) on 3 grade-1 Lessons.
2. A progress bar shows while it runs. The pilot finishes and opens Content Review → Kiểm tra ngẫu nhiên (spot-check), where Anh marks each sampled Answer Key right or wrong. That sets the accuracy figure for the gate.
3. **Climax:** the go/no-go report shows three green checks and a cost estimate. Anh taps "Chạy toàn bộ", and the full run proceeds in the background and can be resumed.

**Failure:** if a gate fails (for example fallback is 22%), the report lists which layouts failed and "Chạy toàn bộ" stays disabled.
