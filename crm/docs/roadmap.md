# CRM canonical continuation roadmap

Last updated: 2026-10-08
Target branch: `crm-v1`
Current canonical head before active slice: `e4820454353f43c2c1f50b904d29f2f72cf62354`
Current observed production live commit before active slice: `c92b43d98d25b45417037886d6cba5adc24cd994`

This file is the canonical staged plan. Read together with `HANDOFF.md`. Do not restart the analysis from zero after a chat reset.

## Product contract

Generic SaaS-ready CRM for schools/clubs/studios. AeroKids is the first tenant, not a fork.

Non-negotiable invariants:
- tenant isolation on every owned relation;
- OrganizationMembership is authorization source of truth;
- Staff is worker profile;
- teachers assigned-group scoped by default;
- GET endpoints do not mutate business data;
- finalized attendance is the billing boundary;
- historical rosters and financial history remain reproducible;
- organization-local time governs business dates;
- production fails closed instead of showing demo data.

## DONE — Stage 1 Core Hardening

Reference: PR #45.

Completed: RBAC/access synchronization, credential-bound JWT invalidation, tenant FK guards, rooms/resources, recurring schedule reconciliation/history, historical enrollment roster, individual lessons, trial conflicts, archive/pause/resume lifecycle, finalization/reopen + billing reconciliation, idempotent renewals, tariff snapshots, privacy tooling, invariant audit, backup/restore scripts, browser/PostgreSQL/security CI.

## DONE — Production operations baseline

References: PR #46 and #47.

Completed:
- Render production deploy;
- structured logs/request IDs;
- `/health` + `/ready`;
- daily maintenance endpoint;
- GitHub Actions scheduler with OIDC;
- invariant checks after maintenance;
- incident-response docs;
- production DB integrity audit.

## IN PROGRESS — Stage 2 maintainability/UI architecture

Merged through PR #74:
- frontend API contracts/client/auth foundation;
- shared utilities and editor primitives;
- Login, AuditHistory, Leads board/table;
- role-aware shell helpers;
- group candidate matching and schedule presentation helpers;
- feature projection/adapters;
- Staff, Locations, Settings, Reports views;
- GroupsView;
- StudentsView + StudentDrawer;
- backend services extracted for audit, contacts, groups, locations, organizations, reporting, staff, students and trials;
- compatibility wrappers preserved in `services/crm.py`.

Completed slices:
- ScheduleView extraction — PR #71;
- AttendanceView extraction — PR #72;
- PaymentsView extraction — PR #73.

Completed since the previous roadmap update:
- StaffDrawer extraction — PR #74.

Current active slice:
- extract billing dialogs from App into the billing feature module;
- preserve financial behavior;
- browser smoke coverage;
- refresh persistent handoff/roadmap.

Next slices, in order:
1. Remaining large lead/group/location/billing drawers and modals from App.
2. Re-measure App.tsx and extract the largest remaining behavior-preserving UI block.
3. Scheduling service extraction from legacy `crm.py`.
4. Billing legacy-service extraction.
5. Re-measure `App.tsx` and `crm.py`; Stage 2 ends only when remaining orchestration is readable and domain logic is not concentrated in either file.

Rules:
- one behavior-preserving slice per PR;
- full CI/E2E before merge;
- no UI/business-rule redesign hidden inside modularization PRs.

## NEXT — Stage 3 data scale/performance

- server-side pagination/filtering/sorting for students/groups/leads/payments/audit;
- stable list contracts;
- N+1 removal in student/group detail;
- query-count/performance tests;
- index review;
- bounded reports;
- paginated UX states.

## NEXT — Stage 4 permissions UX

- role preset editor;
- effective capability display;
- optional per-user overrides;
- assigned-group scope UX;
- audited changes;
- deactivation clearly removes login access;
- last-owner protection stays mandatory.

## NEXT — Stage 5 tenant onboarding

- generic organization wizard;
- timezone/currency/locale;
- optional locations/rooms;
- staff invite;
- tariff;
- first group or individual setup;
- completion checklist;
- no AeroKids-specific defaults.

## NEXT — Stage 6 communication

- choose transactional email/SMTP provider;
- configure sender/domain;
- enable transport;
- test invite/reset;
- retry/dead-letter/admin delivery visibility.

## NEXT — Stage 7 monitoring/backups/DR

- managed DB backup policy;
- private backup destination and cadence;
- automated periodic restore drill;
- downtime/deploy/DB/invariant alerts;
- latency/5xx/resource dashboard;
- rollback rules.

## NEXT — Stage 8 AeroKids public intake migration

After private production acceptance:
- switch aerokids.space registration to CRM intake;
- preserve anti-spam/rate-limit/duplicate/sibling behavior;
- measure failures;
- keep rollback path.

## LATER — Payments and SaaS commercialization

Payment provider:
- ProviderPaymentAttempt / ProviderTransaction / WebhookEvent;
- unique provider IDs;
- webhook idempotency/signature verification;
- browser redirect never proves payment.

Commercial SaaS:
- plans/feature limits;
- usage metering;
- tenant billing/trial/suspension;
- export before closure;
- support tooling only with audit.

Deferred until foundations are stable:
- MFA/passkeys;
- teacher payroll;
- parent portal;
- homework/content;
- equipment inventory;
- advanced recurrence;
- native mobile app.

## Release acceptance

A slice is DONE only after:
1. merged to `crm-v1`;
2. merged-commit CI green;
3. affected Render service live on exact commit;
4. `/ready` healthy;
5. schema head/invariants verified when relevant;
6. browser/API smoke passes.

## Resume protocol

1. Read `HANDOFF.md` and this roadmap.
2. Check current `crm-v1` head.
3. Check recent merged PRs.
4. Check Render live commits.
5. Skip anything already completed.
6. Continue first unfinished item.
7. Update both files when state materially changes.
