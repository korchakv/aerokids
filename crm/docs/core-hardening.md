# CRM Core Hardening v1

This document is the canonical engineering contract for the hardening stage before broader SaaS rollout.

## Non-negotiable invariants

1. Every tenant-owned object is resolved together with `organization_id`.
2. A tenant-owned relation may never point at an object from another organization.
3. `OrganizationMembership` is the source of truth for organization access; `Staff` is the employee profile.
4. Disabling a linked Staff profile also disables its membership. Staff role and membership role must not drift.
5. The only active owner of an organization cannot be deactivated or demoted.
6. Production RBAC is strict. Teacher access is assigned-group scoped unless explicitly broadened with a capability override.
7. Reading data through GET endpoints must not create or update business records.
8. Historical attendance uses the roster that was enrolled on the lesson date, not today's roster.
9. Students on a learning pause may keep a reserved group seat; reserved seats count toward capacity.
10. Completed lesson-derived billing can only be rolled back automatically while no real payment transaction has occurred.
11. Financial history is corrected through immutable ledger transactions, never by deleting paid history.
12. Subscription tariff behavior is snapshotted. Editing a plan template must not retroactively change an existing subscription's attendance/debt/makeup rules.
13. Automatic renewal is idempotent at both service and database levels.
14. Organization-local dates are used for business deadlines, pauses, reminders and renewals.
15. Production without a configured CRM API fails closed instead of displaying demo students.

## Access model

Baseline role capabilities:

| Role | Default scope |
| --- | --- |
| owner | all capabilities |
| admin | operations, finance, staff, settings, reports, teaching |
| manager | leads, students, groups, schedule, attendance, reports, teaching |
| teacher | teaching and attendance for assigned groups |
| accountant | finance and reports |

Per-staff capability overrides are stored in `staff_capabilities`. Production sets `STRICT_RBAC=true`.

## Staff and account lifecycle

`User` is the login identity. `OrganizationMembership` grants tenant access. `Staff` stores the business profile.

For a linked staff member:

- changing Staff role changes Membership role atomically;
- disabling Staff disables Membership access;
- changing Staff email updates the linked User login email after uniqueness validation;
- access changes are written to AuditEvent;
- password changes invalidate prior JWTs because tokens are bound to the current credential fingerprint.

Production access tokens are limited to 120 minutes by deployment configuration.

## Scheduling model

### Resources

`Location` is a physical site. `Room` is an optional reservable room inside a location. Group, trial and individual lessons may reserve a room and an actual staff member.

When no Room exists, location is treated as the exclusive physical resource for backward compatibility. Once rooms are assigned, different rooms at one location can host simultaneous lessons.

### Recurring schedules

`GroupSchedule` is the current recurring template. `GroupScheduleHistory` records effective historical versions.

Updating a group schedule triggers reconciliation of future, not-yet-conducted lesson sessions:

- future placeholders removed from the recurring template are cancelled, not historically deleted;
- new future sessions are generated;
- location/room/teacher resources are refreshed for untouched future sessions;
- conflict checks are shared with manual lessons, trials and individual lessons;
- completed/history-bearing sessions are never silently rewritten.

GET `/lesson-sessions` is read-only. Recurring materialization/reconciliation runs only through mutating operations or maintenance jobs.

### Trials

Trials now participate in the resource conflict engine and can carry:

- location;
- room;
- actual staff member;
- duration.

### Individual lessons

Students may be active without a group. Individual lessons are first-class records with their own:

- schedule;
- location/room;
- staff;
- attendance;
- subscription usage;
- automatic renewal reconciliation.

No fake one-student group is required.

## Enrollment history and capacity

The legacy unique `(student_id, group_id)` enrollment row is retained for migration compatibility. Each completed episode is copied to `EnrollmentHistory` before the same student returns to that group.

Capacity checks lock the group row on PostgreSQL and count both ACTIVE and PAUSED enrollments. This prevents two concurrent managers from consuming the final seat and treats a paused learner who keeps a seat as occupied capacity.

## Attendance finalization

Attendance is editable, but financial side effects are tied to lesson finalization.

1. Attendance rows are saved.
2. The system verifies the historical lesson-date roster.
3. Once every roster member is marked, the lesson is finalized.
4. Subscription usage, make-up completion and last-lesson renewal are derived.
5. Reopening the lesson reverses only derived, unpaid effects.
6. If a derived charge already has real money transactions, automatic rollback is blocked and staff must make an explicit financial correction.

The explicit `consume_lesson` decision for an absence is persisted in `AttendanceDecision` so reopening/re-finalizing does not lose the manager's choice.

`late` remains readable for historical rows but new late marks are rejected by hardened attendance endpoints.

## Billing and tariff rules

`Payment` is a charge. `PaymentTransaction` is immutable money movement.

`SubscriptionRuleSnapshot` freezes the tariff behavior that applies to an existing subscription:

- usage mode;
- absence rule;
- excused absence/makeup rule;
- late rule;
- end rule;
- renewal trigger;
- debt allowance;
- late limit;
- makeup expiry.

Before a plan template is edited, missing snapshots for its existing subscriptions are created. A deliberate mid-period plan change explicitly updates the affected subscription's snapshot to the new plan.

An `allow_debt=false` subscription does not supply lesson entitlement while its linked charge has an outstanding balance.

Automatic renewal uses a partial unique database index on active renewal children and locks the parent subscription row during renewal.

## Privacy

Owner-only anonymization is available for archived students after active enrollment and outstanding debt have been cleared.

The anonymizer:

- removes student PII and free-text notes;
- removes private lesson/attendance notes;
- disables auto-renewal;
- anonymizes an orphaned responsible contact, but preserves a shared parent/contact used by a sibling;
- retains accounting and attendance structure required for historical integrity;
- records an audit event.

A JSON student data export includes linked contacts, enrollment history, attendance, subscriptions, payments, ledger transactions and audit history.

Retention candidates can be listed by age; the application intentionally does not auto-delete financial history.

## Transactional email

Invitation and password-reset messages are written to `notification_outbox`. Optional SMTP delivery is controlled by `TRANSACTIONAL_EMAIL_ENABLED` and SMTP environment variables.

After a successful send, the token-bearing link is removed from the persisted outbox payload. Existing API responses still expose the one-time token for backward-compatible admin UI until the frontend migrates fully to email-only delivery.

## Maintenance

Run daily maintenance with:

```bash
cd crm/backend
python -m app.jobs.daily_maintenance
```

It performs:

- future recurring schedule reconciliation;
- subscription renewal checks;
- missing tariff-rule snapshot backfill;
- stale login/public-intake throttle cleanup;
- pending transactional email delivery when enabled.

The job is idempotent. It may be attached to a scheduler without changing its business rules.

## Database invariant audit

Run:

```bash
cd crm/backend
python -m app.jobs.audit_invariants
```

The command is read-only and exits non-zero for critical integrity violations. CI runs it against the smoke database.

It checks cross-tenant relations, group capacity, staff/membership drift, duplicate renewal children, payment-ledger status consistency and other structural invariants.

## Production frontend

Production builds require `VITE_API_URL`. Demo fallback is allowed only when explicitly enabled with `VITE_DEMO_MODE=true`.

Browser CI covers desktop and iPhone-size smoke flows in addition to API smoke tests.

## Remaining infrastructure choices

The repository contains the application-side mechanisms for daily maintenance, transactional email and backup/restore. External credentials and scheduler ownership are deployment settings, not code defaults. Do not commit provider credentials to the repository.
