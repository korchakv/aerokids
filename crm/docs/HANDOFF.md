# CRM canonical handoff

Updated: 2026-10-07
Canonical product branch: `crm-v1`
Current production-hardening merge: `c0f8ff24588a6e0a1995d28ba474a5f97c608522`
Continuation branch: `crm-post-hardening-v1`

This file is the canonical continuation point for future ChatGPT/project sessions. Read it together with `architecture.md`, `core-hardening.md`, `status.md`, and `backup-restore.md` before making structural CRM changes.

## Product direction

The CRM is a generic SaaS-oriented product for schools, clubs and learning organizations. AeroKids is the first tenant, not a fork-specific implementation. The architecture must continue to support multiple organizations, locations, rooms, employees and teachers without breaking tenant isolation.

The system remains a modular monolith. Do not split it into microservices unless a measured production need appears.

## Core invariants already completed

The Core Hardening phase was merged through PR #45 into `crm-v1`.

Completed:
- strict production RBAC;
- teacher scope limited to assigned groups while teaching actions remain possible in assigned groups;
- synchronized Staff / User / OrganizationMembership access state;
- protection against removing the last organization owner;
- JWT invalidation when credentials change;
- shorter production JWT lifetime;
- tenant-scoped validation for billing, groups, staff, locations and hardening resources;
- rooms and room assignment groundwork;
- lesson resource assignment with actual teacher/room snapshot;
- trial resource conflicts;
- recurring schedule reconciliation and schedule history;
- no database mutation from lesson-session GET;
- historical enrollment/roster logic;
- non-overlapping transfer intervals;
- pause/resume/archive learning workflows;
- group archive lifecycle;
- individual lessons, attendance and subscription usage;
- lesson finalization/reopen controls;
- attendance decisions and deterministic billing reconciliation;
- renewal idempotency and concurrency guard;
- organization-local billing dates;
- paused enrollments reserve capacity where configured;
- subscription tariff rule snapshots;
- privacy export and anonymization;
- transactional notification outbox;
- request IDs and hardened forwarded-IP handling;
- explicit production demo-data guard;
- search/pagination foundation;
- read-only database invariant auditor;
- daily maintenance job;
- PostgreSQL backup and restore-drill scripts;
- desktop/mobile Playwright smoke tests;
- security/dependency/secrets CI;
- updated canonical architecture documentation.

## Validation already completed

The PR and the post-merge commit both passed:
- backend compile and pytest;
- Alembic migrations;
- invariant auditor;
- PostgreSQL full test suite;
- clean PostgreSQL migration test;
- frontend TypeScript/Vite build;
- Docker Compose validation and backend/frontend image builds;
- Python dependency/security audit;
- frontend npm audit;
- secret scan;
- API end-to-end smoke flow;
- live smoke-database invariant audit;
- Playwright desktop and mobile browser smoke.

## Production deployment state at handoff

Render services:
- API: `aerokids-crm-api`
- frontend: `aerokids-crm`
- branch: `crm-v1`
- auto-deploy mode: checksPass

At the moment this handoff was written, Render still showed the previous live commit `86cbc739...`, while GitHub `crm-v1` already pointed to `c0f8ff2...` and all post-merge GitHub checks were green.

Therefore the first operational continuation task is to confirm Render has deployed `c0f8ff2...`. Do not claim production is updated until both Render services report the new commit as live.

## Remaining Phase 2 work

### P0 production operations
1. Confirm API and frontend Render deployment of `c0f8ff2...`.
2. Verify `/ready` and production login/bootstrap-safe behavior after deployment.
3. Run a read-only invariant audit against the actual production database.
4. Confirm Alembic production head equals repository head.
5. Verify no tenant cross-links, over-capacity groups, contradictory Staff/Membership state, duplicate primary contacts, duplicate renewal chains or financial inconsistencies.

### P1 scheduled operations
1. Run daily maintenance independently of a user opening the CRM.
2. Maintenance includes renewal reconciliation, pause/resume lifecycle, reminder queue/outbox delivery, stale rate-limit cleanup and integrity checks as appropriate.
3. Use a server-side scheduler/cron with idempotent commands. Never make GET endpoints perform scheduled writes.
4. Avoid copying database credentials into source code.

### P1 observability
1. Keep request IDs end-to-end.
2. Add structured application logs for request failures and scheduled jobs.
3. Define production error/5xx and failed-deploy checks using available Render monitoring.
4. Keep health/readiness endpoints inexpensive and side-effect free.
5. Document an incident checklist and rollback path.

### P1 transactional email
1. Outbox logic exists, but production email transport must remain disabled until SMTP/provider settings are configured.
2. Verify invite and password-reset delivery end-to-end once credentials exist.
3. One-time auth tokens must not remain indefinitely in outbox payload after successful send.

### P1 code modularization
Do this only after production hardening is live and stable.
- split backend `services/crm.py` by domain without changing public behavior;
- split frontend `App.tsx` into feature modules;
- split `api.ts` by domain;
- keep one shared API client/auth layer;
- move feature-specific state and views under Leads, Students, Groups, Schedule, Attendance, Billing, Staff and Settings modules;
- retain E2E coverage while moving code;
- refactor in small PRs, never one giant rewrite.

### P2 SaaS readiness
- organization onboarding/presets;
- role + capability UI;
- room management UI;
- scalable server-side filters/sorting/pagination;
- operational backup/restore drills;
- privacy/retention policy UI and support tooling;
- payment-provider webhook idempotency layer before LiqPay/WayForPay integration;
- transactional email provider;
- monitoring/alerts;
- optional MFA/session management later;
- resource planning can later generalize rooms/teachers to equipment, but do not over-engineer it now.

## Important business rules to preserve

- Student CRM funnel status and learning lifecycle are different concepts.
- A student may learn without a group/location through individual lessons.
- Historical lesson participation must be determined by the enrollment period at the lesson date, not only current group membership.
- Completed/historical lessons must not be silently rewritten when a recurring schedule changes.
- A finalized lesson is the billing boundary; reopening is an audited exceptional action.
- Subscription price and behavior are snapshots; editing a tariff template must not retroactively alter sold subscriptions.
- Financial history uses charges + immutable transactions/adjustments, not a mutable single balance field.
- Organization-local timezone is authoritative for business dates.
- Tenant-owned foreign keys must never cross organizations.
- Production must fail closed when required API/auth configuration is missing; never show demo students as a production fallback.

## Workflow for all future changes

1. Start from current `crm-v1`.
2. Work in a dedicated branch/PR.
3. Preserve migrations and backward compatibility.
4. Add regression tests for every corrected invariant.
5. Require full CI green before merge.
6. After merge, verify actual Render deployment and health.
7. Update this handoff file when a phase is completed or priorities change.
