# CRM canonical continuation roadmap

Last updated: 2026-10-07
Target branch: `crm-v1`
Current production baseline commit: `172124a210b395f1e8fed6b510590a98ca33b83f`

This file is the canonical handoff for continuing CRM work after chat/context resets. Do not restart analysis from zero. Read this file together with `docs/core-hardening.md`, `docs/operations.md`, `docs/backup-restore.md`, and `docs/status.md`.

## Product contract

The CRM is a generic SaaS-ready product for schools, clubs and studios. AeroKids is the first tenant, not a fork.

Core entities:
- Organization
- User / OrganizationMembership / Staff
- Location / Room
- Contact / Student / StudentContact
- Group / Enrollment / EnrollmentHistory
- GroupSchedule / LessonSession / individual lessons
- Attendance / make-up state
- SubscriptionPlan / StudentSubscription
- Payment / immutable PaymentTransaction
- AuditEvent

Core rules:
- tenant isolation is mandatory on every owned relation;
- OrganizationMembership is the access source of truth;
- Staff is the worker profile, not the authorization record;
- teachers are assigned-group scoped by default;
- GET endpoints must not mutate business data;
- attendance and billing side effects happen through controlled finalization/reconciliation;
- historical rosters and financial history must remain reproducible;
- organization-local time governs business dates;
- production must never fall back to demo data.

## DONE — Core Hardening

Completed and merged:
- strict production RBAC;
- Staff/User/Membership synchronization;
- access revocation after staff deactivation;
- credential-bound JWT invalidation after password change;
- cross-tenant subscription/group/resource validation;
- rooms and resource conflict engine;
- recurring schedule reconciliation and schedule history;
- historical enrollment episodes and lesson-date roster;
- paused-seat capacity rules and concurrency-safe enrollment;
- individual lessons without fake one-person groups;
- trial lesson resource conflicts;
- group archive lifecycle;
- actual lesson staff/room resource assignments;
- attendance finalization/reopen;
- make-up reconciliation;
- billing rollback protection after real money movement;
- idempotent subscription renewal;
- per-subscription tariff-rule snapshots;
- organization-local renewal/reminder/pause dates;
- privacy export / retention candidates / anonymization;
- read-only invariant auditor;
- backup and isolated restore-drill scripts;
- production API fail-closed without VITE_API_URL;
- desktop + mobile Playwright smoke;
- SQLite + PostgreSQL full test suites;
- Docker builds, dependency audit and secret scan.

Reference merge: PR #45.

## DONE — Production operations

Completed and live:
- Render API + frontend production deploy;
- structured JSON application logs;
- request IDs;
- /health and /ready operational checks;
- daily idempotent maintenance endpoint;
- GitHub Actions scheduled maintenance;
- GitHub OIDC authentication for maintenance, no shared production secret required;
- invariant audit after maintenance;
- scheduled maintenance fails on critical integrity findings;
- incident-response documentation.

Reference merges: PR #46 and PR #47.
Production baseline at the time of this roadmap: `172124a...`.

## IN PROGRESS — Stage 2: maintainability and UI architecture

Goal: reduce regression risk before adding more commercial SaaS features.

Progress:
- PR #48 merged: API contracts/client/auth split, shared UI/date/contact utilities extracted, LoginView, AuditHistory, schedule editors and lead Kanban/table moved out of App.tsx; App.tsx reduced substantially with full CI/E2E green.
- Current Stage 2 domain-module branch: group, teaching, billing, staff, location and workspace/operations projection models/adapters are being extracted from App.tsx.

Required:
1. Continue splitting `frontend/src/App.tsx` into feature modules without changing behavior. **In progress.**
2. Split frontend API/types by domain while keeping a compatibility barrel. **Foundation complete; domain-specific API façades remain.**
3. Continue decomposing legacy `backend/app/services/crm.py`; hardened services are already split, but legacy flows remain too large. **Not started.**
4. Keep every extraction behavior-preserving and protected by CI/E2E. **Active release rule.**
5. Add targeted browser tests when moving a feature out of App.tsx. **Existing full desktop/mobile smoke retained; feature-specific coverage to expand.**

Recommended frontend domains:
- app shell / navigation
- auth/bootstrap
- leads
- students
- groups
- schedule
- attendance
- billing
- staff
- settings
- shared modals/forms/components

Recommended backend domains:
- organizations
- contacts/students
- leads/trials
- groups/enrollment
- scheduling
- billing
- staff
- audit/reporting

## NEXT — Stage 3: data scale and performance

Foundation exists but is not complete.

Required:
- real server-side pagination for large student/group/lead/payment/audit lists;
- server-side filtering and sorting;
- stable pagination contract (limit/offset initially; cursor only where needed);
- indexes reviewed against real query patterns;
- remove N+1 paths in group/student detail;
- query-count/performance regression tests;
- bounded report queries;
- UI loading/empty/error states for paginated screens.

Do not load all students into the browser once organizations become large.

## NEXT — Stage 4: organization permissions UX

Backend capability overrides exist; product UX is incomplete.

Required:
- permission preset editor;
- presets: Owner, Admin, Manager, Teacher, Accountant;
- optional per-user overrides;
- assigned-groups-only toggle/scope where applicable;
- visible explanation of effective permissions;
- audit every access change;
- prevent the last owner from losing ownership/access;
- staff deactivation must clearly show that login access is removed.

## NEXT — Stage 5: organization onboarding

Required before commercial multi-tenant rollout:
- guided organization creation;
- organization basics: name, timezone, currency, locale;
- locations optional;
- invite first staff;
- create first tariff;
- create first group or individual-learning setup;
- checklist showing incomplete setup;
- no AeroKids-specific defaults in generic tenant flows.

## NEXT — Stage 6: production communication

Application outbox exists, but provider-side delivery is deployment configuration.

Required:
- choose transactional email provider / SMTP;
- configure sender/domain;
- enable `TRANSACTIONAL_EMAIL_ENABLED`;
- test invite and password-reset deliverability;
- retry/dead-letter visibility for failed outbox messages;
- admin-friendly delivery status;
- never persist raw one-time tokens after successful send.

Later channels:
- Telegram/SMS/Viber/WhatsApp only through provider-neutral notification jobs.

## NEXT — Stage 7: monitoring, backups and disaster recovery

Application mechanisms exist. External operations must be completed:
- managed database backup policy confirmed;
- private backup destination;
- scheduled backup cadence;
- periodic automated restore drill;
- alert ownership for API downtime, deploy failure, DB availability and critical invariant audit failures;
- basic latency / 5xx / saturation dashboard;
- documented rollback decision rules.

## NEXT — Stage 8: public website intake migration

Do only after private production acceptance:
- point `aerokids.space` registration form to CRM public intake;
- preserve honeypot and rate limiting;
- ensure repeat/sibling submissions behave correctly;
- measure intake failures;
- keep rollback path to previous form transport during initial rollout.

## LATER — Stage 9: payment provider integration

Do not weaken the current immutable ledger.

Provider model must include:
- ProviderPaymentAttempt;
- ProviderTransaction;
- WebhookEvent;
- unique provider event/transaction IDs;
- webhook idempotency;
- provider signature verification;
- browser redirect is never proof of payment;
- manual and provider payments reconcile into the same PaymentTransaction ledger.

## LATER — Stage 10: commercial SaaS controls

After operational stability:
- plan/feature limits per organization;
- usage metering;
- organization billing;
- trial period;
- suspend/reactivate tenant;
- export before account closure;
- support/admin tooling with audited impersonation only if truly necessary;
- legal/privacy docs and retention commitments.

## Deferred, not forgotten

- MFA / passkeys;
- richer reporting;
- teacher payroll;
- homework/content tracking;
- equipment/resource inventory;
- advanced recurrence engine;
- parent portal;
- mobile app.

These should not be started before Stage 2–7 foundations are stable unless a real customer requirement changes priority.

## Release acceptance rule

A stage is not DONE until:
1. code is merged to `crm-v1`;
2. CI is green on the merged commit;
3. Render API and frontend are live on that exact commit when affected;
4. /ready is healthy;
5. Alembic is at repository head when schema changed;
6. production invariant audit has no critical findings;
7. affected browser/API flows are smoke-tested.

## Continuation protocol

When resuming work:
1. read this file;
2. check current `crm-v1` head;
3. check recent merged PRs after the commit above;
4. check Render live commits;
5. mark already-completed roadmap items DONE instead of rebuilding them;
6. continue with the first unfinished item;
7. update this file whenever a stage materially changes.
