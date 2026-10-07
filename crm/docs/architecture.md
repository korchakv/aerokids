# CRM architecture

## Product boundary

CRM is a reusable multi-tenant product for schools, clubs and learning centers. AeroKiDS is the first tenant and product-validation environment, not a separate code edition.

The application remains a modular monolith:

- FastAPI application/API layer;
- domain services for CRM, scheduling, attendance, enrollment, billing, auth and privacy;
- SQLAlchemy/PostgreSQL persistence;
- Alembic migrations;
- React frontend.

Do not introduce microservices for ordinary product features.

## Tenant boundary

`Organization` is the tenant boundary.

Every tenant-owned business row carries `organization_id`. A request organization is accepted only together with an authenticated active `OrganizationMembership` in production.

Service code must resolve foreign tenant-owned IDs with both object ID and `organization_id`. The invariant auditor independently checks for cross-tenant relationships.

## Identity, staff and authorization

The three concepts are separate:

- `User` — global login identity;
- `OrganizationMembership` — access to one organization and its authorization role;
- `Staff` — employee/business profile inside one organization.

`OrganizationMembership` is the access source of truth. For linked staff, role and activation changes synchronize between Staff and Membership. A password change invalidates previously issued JWTs through a credential fingerprint embedded in the token.

Production uses strict role/capability checks. Role presets provide defaults; `StaffCapability` stores explicit per-staff overrides.

## CRM funnel without a Lead table

There is no separate Lead entity.

An intake creates/links:

- `Contact`;
- `Student`;
- `StudentContact`.

`Student.crm_status` is the sales/communication stage. `Student.student_status` is the learning lifecycle (`prospect`, `active`, `paused`, `archived`). These concepts must never be collapsed into one status.

Deferred follow-up is stored independently from closing/outcome data.

## Enrollment model

`Enrollment` is the current group relationship. A learner may also be active without a group for individual learning.

The legacy unique student/group enrollment row is retained for compatibility. When the same learner later returns to the same group, the previous enrollment period is first copied to `EnrollmentHistory` and the current row starts a new episode.

ACTIVE and PAUSED enrollments both reserve group capacity unless the pause workflow explicitly releases the seat by finishing the enrollment.

## Location and resource model

`Location` is a site. `Room` is an optional reservable room within a site.

Scheduling can reserve:

- location;
- room;
- actual staff member.

When rooms are not configured, location remains the exclusive physical-resource fallback. This preserves small-school behavior while allowing larger schools to run simultaneous classes in different rooms.

## Scheduling model

`GroupSchedule` is the current recurring template.

`GroupScheduleHistory` stores effective historical versions. Concrete `LessonSession` rows represent actual lessons.

Rules:

1. GET requests never materialize lessons.
2. A schedule mutation reconciles future uncompleted sessions.
3. Historical/completed sessions are not rewritten to match a new template.
4. Manual group lessons, recurring group lessons, trial lessons and individual lessons share one resource-conflict model.
5. Actual staff/room for group lessons are snapshotted through `LessonResourceAssignment` so later group staffing changes do not destroy lesson history.

`TrialResourceAssignment` adds teacher, room and duration to the existing TrialLesson model without rewriting old historical rows.

## Attendance model

A group lesson's eligible roster is calculated using enrollment periods at the lesson date, not today's group membership.

Attendance rows are the factual marks. `AttendanceDecision` stores additional billing choices such as whether an ordinary absence consumes a lesson.

Financial/makeup side effects are derived when a lesson is finalized. `LessonFinalization`, `LessonDerivedBilling` and `MakeupCompletionLink` make those effects reversible while they have not crossed into real paid financial history.

When a derived charge has already received/refunded real money, reopening is blocked until an explicit financial correction is made.

## Individual learning

An active student does not need a group or location.

`IndividualLessonSession`, `IndividualAttendance` and `IndividualSubscriptionUsage` provide a complete individual-learning flow using the same subscription/billing concepts as group learning.

This avoids fake one-person groups.

## Subscription and financial architecture

`SubscriptionPlan` is the reusable tariff template.

`StudentSubscription` snapshots the purchased period/lesson/price values. `SubscriptionRuleSnapshot` additionally freezes behavioral rules such as absence, makeup, debt and renewal semantics so template edits never silently rewrite already sold subscriptions.

`Payment` is a charge (what the family owes). `PaymentTransaction` is immutable money movement/correction.

The application derives adjusted charge, received amount, refunds, balance and credit from the ledger. Paid history is never deleted to repair mistakes.

Automatic renewals use `renewal_of_id`, service-level locking and a database partial unique index so one parent has at most one active renewal child.

## Public intake

Public endpoint:

`POST /public/intake/{organization_slug}`

It provides:

1. database-backed IP and normalized-phone rate limiting;
2. honeypot handling;
3. phone normalization;
4. Contact reuse;
5. same-child duplicate protection while allowing siblings to share a responsible contact;
6. Student + StudentContact creation/linking;
7. CRM status initialization;
8. source/audit recording.

Public intake and login use hardened proxy-aware client-IP extraction for throttling.

## Privacy boundary

Student data export is available through a tenant-scoped endpoint. Anonymization is owner-controlled and only allowed after the student is archived and financial/enrollment blockers are resolved.

Accounting and historical structural rows are retained; unnecessary PII/free text is removed. Shared responsible contacts used by another child are preserved.

## Operational integrity

`python -m app.jobs.audit_invariants` is a read-only structural audit. It validates tenant relationships, capacity, access/profile drift, renewal uniqueness and payment-ledger consistency.

`python -m app.jobs.daily_maintenance` is the idempotent unattended-maintenance entrypoint for future schedule reconciliation, renewals, rule-snapshot backfill, throttle cleanup and optional transactional-email delivery.

Backup/restore policy is documented in `docs/backup-restore.md`.

## Frontend/runtime boundary

`VITE_API_URL` is mandatory for a production build. The production UI fails closed rather than silently falling back to demo records. Demo mode requires explicit `VITE_DEMO_MODE=true`.

The frontend remains a React SPA; feature decomposition may proceed incrementally without changing the backend domain model.

## Current hardening specification

See `docs/core-hardening.md` for the detailed invariant and workflow contract.
