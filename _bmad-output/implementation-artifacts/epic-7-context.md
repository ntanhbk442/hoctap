# Epic 7 Context: Paper worksheets and safe data

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

After this epic Anh can print any Problem Set as an A4 worksheet with a separate answer page, for practice away from the tablet (for example a weekend trip), and can back up and restore all of Bin's progress so a PC failure does not lose it. Printing is a parent-side convenience; backup protects the only copy of the data, which lives on the home PC.

## Stories

- Story 7.1: Printable worksheets
- Story 7.2: Backup and restore

## Requirements & Constraints

- A parent can print any Problem Set (problems plus an answer page) using the browser's print function or "Save as PDF"; there is no server-side PDF requirement.
- Interactive Problem Types print in a paper-friendly form: empty boxes for answer slots, and dots to connect for `match`. Output is A4 and black-and-white safe (no colour-only meaning).
- The answer page follows a page break; the Answer Key never appears on the problem pages.
- Every Problem Type, including `expression_input`, must be printable; a new type ships its print renderer with its schema, grader and widget.
- Backup is a single `.db` file made while the app keeps running; progress is already saved after every Attempt.
- Restore is refused while a build job runs. It puts the app into maintenance (503), replaces the database, runs migrations, rotates the cookie key, bumps `db_epoch`, and returns; tablets discard outbox events stamped with the old `db_epoch`.
- Data stays on the home PC; all screens are Vietnamese with correct diacritics.

## Technical Decisions

- `learning.problem_sets.resolve()` is the only definition of "the Problems in this set"; printing uses it, so a worksheet always matches what a Session would contain.
- Problems, Parts and slots are addressed by `problem_id`, `part_key`, `slot_key`; the effective doc (extraction merged with review overrides) is the content source, and crops are served from the assets route.
- Parent-only routes sit behind the PIN cookie; anything carrying answers is parent-only. `child_view()` stays the only child projection.
- Backup uses the SQLite online backup API (WAL mode); restore handling follows the maintenance-mode, migration and key-rotation sequence in the architecture.
- Schema changes go through Alembic migrations with module table prefixes.

## UX & Interaction Patterns

- Parent Library rows offer "Giao bài", "In phiếu" and "Xem"; "In phiếu" opens a print preview (worksheet plus answer page) from which the parent prints or saves as PDF.
- Print CSS: A4, black-and-white safe, empty answer boxes, answer page after a page break, dots for `match`.
- Settings hosts "Sao lưu" and "Khôi phục" with a confirmation step for restore.

## Cross-Story Dependencies

- Story 7.1 builds on the print stub from Story 6.1, the Problem Set resolver (Epics 2-5) and the parent preview of Problems (Epic 4).
- Story 7.2 depends on the builder job state (Epic 1/6) to refuse restore during a build, and on the PWA event outbox (Epic 2) for `db_epoch`.
