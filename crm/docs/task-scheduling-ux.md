# Active task — Scheduling UX, soft availability and group matching

Status: ready for implementation  
Scope: `crm/` only  
Branch: `crm-v1`

## Product problem

Current scheduling UX is too rigid and inconvenient:

- group schedule is entered as free text like `Пн / Ср · 17:00`;
- date/time inputs allow minute-level precision that is unnecessary for this product;
- student availability is treated too literally, although parents usually provide approximate preferred windows;
- group formation currently reports only that a schedule does not match, without showing when it *does* match;
- a schedule conflict must never block enrollment/group creation, because managers may still negotiate a slightly different time with a parent.

The CRM must treat family schedule information as a **soft preference**, not a hard constraint.

## UX goals

1. No free-text schedule entry for groups.
2. Use consistent visual day/time controls everywhere.
3. Time selection uses 15-minute increments only.
4. Student availability is represented as approximate windows.
5. Group matching returns `match`, `partial`, `conflict`, or `unknown`.
6. A mismatch is a warning only. It never disables group creation or enrollment.
7. When a child is selected for a group, show:
   - group schedule;
   - family preferred windows;
   - exact matching windows;
   - useful explanation if the match is partial/conflicting.
8. Persist a short schedule-matching note with the enrollment/audit history so staff can see what was agreed later.
9. Preserve multi-tenant isolation and all existing permissions.

---

# 1. Database changes

## 1.1 Student availability becomes a soft preference

Existing model: `StudentAvailability`.

Add enum:

```python
class AvailabilityPreference(str, enum.Enum):
    PREFERRED = "preferred"
    POSSIBLE = "possible"
    AVOID = "avoid"
```

Add columns:

```python
preference: Mapped[AvailabilityPreference] = mapped_column(
    Enum(AvailabilityPreference),
    default=AvailabilityPreference.PREFERRED,
    nullable=False,
)
note: Mapped[str | None] = mapped_column(String(300))
```

Keep:
- `weekday`
- `start_time`
- `end_time`

Existing rows migrate to `preferred`.

These are **preferences**, not hard availability rules.

## 1.2 Enrollment matching note

Add nullable fields to `Enrollment`:

```python
schedule_match: Mapped[str | None] = mapped_column(String(20))
schedule_note: Mapped[str | None] = mapped_column(Text)
```

Allowed `schedule_match` values:
- `match`
- `partial`
- `conflict`
- `unknown`

Do not create a separate microservice/entity just for matching.

## 1.3 Migration

Create a new additive Alembic migration after the current head.

Requirements:
- PostgreSQL compatible;
- SQLite CI compatible;
- never rewrite already-applied migrations;
- downgrade supported.

---

# 2. Shared time rules

Introduce a single backend/frontend rule:

**All manually selected times use 15-minute increments.**

Examples:
`08:00, 08:15, 08:30, 08:45, ... 21:45`

Do not use native browser minute spinners as the main UX.

Create reusable frontend helpers/components instead of duplicating logic:

```text
TimeSelect
WeekdaySelect / WeekdayChips
ScheduleSlotEditor
AvailabilityWindowEditor
DateSelect / DateTimeEditor
```

Recommended time range for the UI:
- default: 08:00–21:45;
- component may accept `minTime` and `maxTime`;
- keep backend generic.

Backend validators should reject times that are not on a 15-minute boundary for user-created:
- GroupSchedule;
- StudentAvailability;
- TrialLesson start;
- LessonSession start.

Existing old records must remain readable.

Duration is separate from start time:
- 45 min
- 60 min
- 75 min
- 90 min

Default = 60 min.

Do not require duration to be a multiple of 15 in the DB, but UI choices should be 15-minute increments.

---

# 3. Group formation UX

Replace the current free-text field:

`Розклад: Пн / Ср · 17:00`

with a structured schedule builder.

## Required layout

Header:
`Розклад групи`

Each row:

```text
[ День ▼ ] [ Початок ▼ ] [ Тривалість ▼ ] [ Видалити ]
```

Example:

```text
Пн | 17:00 | 60 хв
Ср | 17:00 | 60 хв
```

Button:

`+ Додати день`

The group can have 1..N schedule slots.

Do not serialize the UI into free text and parse it back.
Frontend state must be structured:

```ts
type DraftScheduleSlot = {
  weekday: number;
  start_time: string;
  duration_minutes: number;
};
```

POST `/groups/form` already supports `schedule_slots`; use this directly.

Prevent exact duplicate slots in the UI and backend.

---

# 4. Trial lesson / normal lesson date-time UX

Replace raw `datetime-local` where practical with:

```text
Дата: [ 15.10.2026 ]
Час: [ 17:00 ▼ ]
Тривалість: [ 60 хв ▼ ]   // for lesson sessions
Локація: [ ... ▼ ]
```

For trial lessons duration can remain implicitly ~60 min unless the domain model later stores duration.

Time dropdown = 15-minute increments.

Keep storage/API as ISO datetime in organization timezone / UTC according to current app conventions.

Timezone correctness:
- UI uses organization timezone;
- database timestamps remain timezone-aware;
- do not hardcode Europe/Kyiv in scheduling logic.

---

# 5. Student preferred schedule UX

Current student preference UI is too exact and too limited.

Replace it with multiple independent **preferred windows**.

Each window:

```text
День:      [ Пн ▼ ]
Від:       [ 16:30 ▼ ]
До:        [ 19:00 ▼ ]
Пріоритет: [ Бажано ▼ ]
Коментар:  [ optional ]
```

Priorities in Ukrainian UI:

- `Бажано` → `preferred`
- `Можливо` → `possible`
- `Небажано` → `avoid`

Button:
`+ Додати ще варіант`

Copy above the editor must explicitly communicate:

> Це орієнтовні побажання сім’ї. Фінальний графік узгоджується під час формування групи.

Do not label this as strict “availability”.

The manager can save zero windows = `unknown`.

Location preference remains optional:
`Бажана локація`.

---

# 6. Matching algorithm

Implement the core algorithm on the **backend service layer** so frontend and future integrations use one source of truth.

Create a pure/testable function/service such as:

```python
evaluate_schedule_match(
    group_slots,
    student_windows,
    group_location_id=None,
    preferred_location_id=None,
) -> ScheduleMatchResult
```

Suggested result:

```python
class ScheduleMatchResult:
    status: Literal["match", "partial", "conflict", "unknown"]
    matching_slots: list[...]
    partial_slots: list[...]
    conflicting_slots: list[...]
    summary: str
```

## 6.1 Definitions

### unknown

Use when:
- student has no preferred windows.

This is not a conflict.

### match

Use when:
- every group schedule slot fits fully inside at least one `preferred` or `possible` window on the same weekday;
- no slot falls inside an `avoid` window;
- location either matches or no preferred location was specified.

### partial

Use when at least one of these is true:
- only some group days fit;
- lesson partially overlaps a preferred/possible window;
- same weekday but group start/end is within **60 minutes** of a preferred/possible window;
- preferred location differs but time matches;
- all slots fit only in `possible`, not `preferred`.

This is intentionally generous because preferences are approximate.

### conflict

Use when:
- there are student preferences, but no group slot matches/overlaps/is near any acceptable window;
- or group slot falls into an explicit `avoid` window with no acceptable alternative.

## 6.2 Important rule

**Never reject group creation, enrollment or transfer because of match status.**

Capacity/tenant/security constraints remain hard rules.
Schedule compatibility is advisory only.

---

# 7. “When does it match?” explanation

The UI must never stop at:

`Графік не збігається`

Instead display useful details.

Examples:

### match

```text
Максим · 9
✓ Графік підходить
Пн 17:00–18:00 — підходить
Ср 17:00–18:00 — підходить
```

### partial

```text
Максим · 9
⚠ Частковий збіг
Пн 17:00 — підходить
Ср 17:00 — сім'я бажає 17:30–19:30
Найближчий варіант: Ср від 17:30
```

### conflict

```text
Максим · 9
! Потрібне узгодження
Група: Пн/Ср 17:00
Побажання: Вт/Чт 18:00–20:00
Збігів немає
```

### unknown

```text
Максим · 9
? Побажаний час не вказаний
Уточнити графік у батьків
```

Use green/yellow/red/neutral visuals, but do not rely on color alone.

---

# 8. Group candidate cards

In `Очікують групу`, every candidate card should show:

- child name;
- age;
- recommended level;
- preferred location;
- compact preferred schedule;
- matching status against the **currently drafted group schedule**.

Matching must update immediately when manager changes:
- day;
- time;
- duration;
- group location.

This should happen without submitting the form.

For frontend instant feedback, it is acceptable to mirror the pure matching rules in TypeScript, but backend remains authoritative and must recalculate on group creation.

Preferred implementation:
- extract equivalent pure functions with the same fixtures;
- backend tests are mandatory;
- frontend unit tests if test framework exists, otherwise keep matching UI helper deterministic.

---

# 9. Enrollment note

When `/groups/form` enrolls selected students:

Backend recalculates schedule match for each student and stores:

`Enrollment.schedule_match`

and a human-readable `Enrollment.schedule_note`.

Example note:

```text
Побажання сім’ї: Пн 17:00–19:00; Ср 17:30–19:30.
Група: Пн 17:00–18:00; Ср 17:00–18:00.
Збіг: частковий. Пн підходить; у Ср група починається на 30 хв раніше.
Потрібно підтвердити фінальний графік з батьками.
```

Also include the result in the audit event payload for `student.enrolled`.

Do not silently overwrite the student's own general notes.

---

# 10. API additions/changes

## Student preferences

Existing endpoints:

```text
GET /students/{student_id}/preferences
PUT /students/{student_id}/preferences
```

Extend schemas to include:

```json
{
  "preferred_location_id": "...",
  "availability": [
    {
      "weekday": 0,
      "start_time": "17:00",
      "end_time": "19:00",
      "preference": "preferred",
      "note": null
    }
  ]
}
```

Keep old clients compatible when `preference` is omitted:
default to `preferred`.

## Group matching preview

Add:

```text
POST /groups/match-preview
```

Role:
- owner
- admin
- manager

Request:

```json
{
  "location_id": "...",
  "schedule_slots": [
    {
      "weekday": 0,
      "start_time": "17:00",
      "duration_minutes": 60
    }
  ],
  "student_ids": ["..."]
}
```

Response:

```json
{
  "students": [
    {
      "student_id": "...",
      "status": "partial",
      "summary": "...",
      "matching_slots": [],
      "partial_slots": [],
      "conflicting_slots": []
    }
  ]
}
```

Tenant scope every student ID.
A foreign-tenant student must return 404/403 consistently with current service conventions.

Frontend may debounce preview calls while editing schedule, or calculate locally and use API preview before final create.

---

# 11. Filters for group formation

Replace purely visual filters with useful filtering:

- age;
- recommended level;
- preferred location;
- schedule match:
  - all
  - match
  - partial
  - conflict
  - unknown.

Add sort:

`Найкращий збіг`

Suggested ordering:

```text
match → partial → unknown → conflict
```

Within the same status:
- closer age range first;
- same preferred location first.

This is a recommendation, not automatic enrollment.

---

# 12. UI component rules

The visual language should remain the current dark School CRM style.

Do not redesign the entire CRM.

Create reusable components, not one-off controls:

```text
<TimeSelect />
<WeekdayPicker />
<DurationSelect />
<ScheduleSlotEditor />
<AvailabilityWindowEditor />
<MatchBadge />
<MatchExplanation />
```

Accessibility:
- all controls keyboard usable;
- labels visible;
- red/green states also have icon/text;
- buttons have disabled states only for invalid form data, not schedule mismatch.

Mobile:
- schedule row collapses cleanly to 1 column / 2 columns;
- candidate explanation remains readable.

---

# 13. Remove old behavior

Remove/stop using:

- manual parsing of `"Пн / Ср · 17:00"` as primary state;
- raw free-text schedule field in group creation;
- minute-by-minute time input;
- schedule mismatch as a blocker;
- generic `Графік не збігається` without explanation.

Legacy display helpers may remain temporarily only for rendering historical data.

---

# 14. Tests

Backend tests are required for both SQLite and PostgreSQL CI.

At minimum cover:

1. availability defaults to `preferred`;
2. 15-minute boundary validation;
3. invalid `end_time <= start_time`;
4. exact match;
5. partial overlap;
6. same-day near match within 60 min;
7. no-overlap conflict;
8. explicit avoid window;
9. unknown with zero preferences;
10. preferred-location mismatch;
11. mismatch does not prevent group formation;
12. enrollment stores `schedule_match` and `schedule_note`;
13. audit event contains matching result;
14. match preview is tenant scoped;
15. cross-tenant student IDs cannot leak;
16. multiple schedule slots;
17. duplicate group slots rejected;
18. existing group formation tests remain green.

Frontend build must remain green.

Full-stack smoke test must remain green.

---

# 15. Acceptance criteria

This task is complete only when all of the following are true:

- no text schedule field remains in group formation;
- manager can add/remove multiple weekly group slots visually;
- all time selectors use 15-minute increments;
- trial/lesson scheduling uses the same reusable time control;
- student schedule is clearly labelled approximate/preferred;
- a student may have multiple preferred windows;
- matching shows match/partial/conflict/unknown;
- UI explains when schedules match and where they differ;
- conflicts do not block group creation;
- enrollment saves an automatic matching note;
- manager can filter/sort waiting students by compatibility;
- backend is authoritative for final match status;
- tenant permissions remain enforced;
- SQLite tests, PostgreSQL tests, migrations, frontend build and full-stack smoke test all pass.

---

# 16. Implementation order

Implement in small cohesive commits:

1. migration + enums/models;
2. Pydantic schemas + validation;
3. backend matching service + unit/service tests;
4. match preview endpoint;
5. group formation persists matching result/note;
6. reusable time/day/duration React components;
7. student preference editor;
8. group schedule builder;
9. candidate match UI + filters/sort;
10. trial/lesson scheduling controls;
11. regression fixes;
12. full CI + full-stack smoke.

Do not touch the public AeroKiDS website or `main`.
Do not connect the production/public website form in this task.
