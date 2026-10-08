# CRM canonical handoff

Updated: 2026-10-08
Canonical product branch: `crm-v1`
Current canonical head before this continuation slice: `81e7e04a08de8c72bd8e44e9cd6273d445672a11`
Current production live commit observed before this slice: `c92b43d98d25b45417037886d6cba5adc24cd994`
Continuation branch: `crm-stage3-pagination-v1`

This is the persistent continuation point for future ChatGPT/project sessions. Read this file together with `roadmap.md`, `architecture.md`, `core-hardening.md`, `operations.md`, `status.md` and `backup-restore.md`. Do not restart the CRM analysis from zero.

## Product direction

The CRM is a generic SaaS-oriented product for schools, clubs, studios and learning organizations. AeroKids is the first tenant, not a separate fork. The system remains a modular monolith. Preserve support for multiple organizations, locations, rooms, employees and teachers and do not weaken tenant isolation.

## DONE — Core Hardening

Merged through PR #45 and retained by all later changes:
- strict production RBAC and assigned-group teacher scope;
- Staff / User / OrganizationMembership synchronization and access revocation;
- last-owner protection;
- credential-bound JWT invalidation and shorter production token lifetime;
- tenant-safe validation for billing/groups/staff/locations/resources;
- rooms and resource conflict engine;
- actual lesson staff/room snapshots;
- trial resource conflicts;
- recurring schedule reconciliation and schedule history;
- side-effect-free GET lesson reads;
- historical enrollment episodes and lesson-date roster;
- pause/resume/archive learning workflows and group archive;
- individual lessons, attendance and subscription usage;
- lesson finalization/reopen and deterministic attendance/billing reconciliation;
- renewal idempotency/concurrency protection;
- organization-local business dates;
- tariff rule snapshots;
- privacy export/anonymization;
- notification outbox;
- request IDs and hardened forwarded-IP handling;
- production demo-data fail-closed behavior;
- pagination/search foundation;
- invariant auditor;
- backup/restore scripts;
- desktop/mobile Playwright, PostgreSQL and security CI.

## DONE — Production operations

Completed after Core Hardening:
- API + frontend deployed on Render;
- structured JSON application logs and request IDs;
- `/health` and `/ready`;
- idempotent daily maintenance endpoint;
- GitHub Actions scheduler authenticated through GitHub OIDC, without a shared cron secret;
- maintenance runs invariant audit and fails on critical findings;
- incident-response documentation;
- privacy-safe production DB audit.

Important scheduler rule: GitHub cron reads workflows from the default branch, so the maintenance workflow must remain available on `main` even while CRM application code is maintained on `crm-v1`.

## DONE — Stage 2 maintainability

Completed through PR #92:
- frontend API contracts/client/auth split with compatibility barrel;
- shared date/contact/editor utilities;
- role-aware shell/navigation helpers;
- feature views for leads, groups, students, staff, locations, settings, reports, schedule, attendance and payments;
- detail drawers and create/edit dialogs extracted into feature modules;
- DashboardView and GlobalSearch extracted from App;
- frontend projections/adapters separated by domain;
- backend domain services extracted for audit, contacts, groups, locations, organizations, reporting, staff, students, trials, scheduling, billing, attendance, lead/intake, enrollment and workspace/detail projections;
- legacy compatibility facade retained in `services/crm.py` so API behavior remains stable.

Stage 2 completion measurements after PR #92:
- `frontend/src/App.tsx`: ~3596 lines, now state/API orchestration rather than a container of large view components;
- `backend/app/services/crm.py`: ~544 lines, now primarily compatibility/orchestration.

Stage 2 is closed. Do not continue extracting code only to reduce line counts unless a concrete maintainability or testability problem justifies it.

## IN PROGRESS — Stage 3 data scale and performance

Active branch/PR:
- `crm-stage3-pagination-v1` / PR #94;
- stable page contract: `{items,total,limit,offset}`;
- database-side pagination/search/sorting for student and group workspace lists;
- regression coverage for assigned-group teacher scope.

After PR #94:
1. wire paginated registry UX without breaking on-demand drawers and global operational flows;
2. add lead pagination/filter/sort using a DB projection instead of N+1 overview loading;
3. add payment and audit pagination;
4. remove remaining N+1 detail/list queries;
5. add query-count/performance tests and index review;
6. bound reports and add paginated loading/empty/error states.

Production note:
- latest observed Render live API/frontend commit before this slice: `c92b43d98d25b45417037886d6cba5adc24cd994`;
- current `crm-v1` is ahead of production after Stage 2 merges, so exact-commit Render rollout and `/ready`/invariant verification are required before Stage 3 production acceptance.



- real server-side pagination for student/group/lead/payment/audit lists;
- server-side filtering and sorting;
- stable pagination contract;
- query/index review against actual paths;
- remove N+1 group/student detail queries;
- query-count/performance tests;
- bounded reporting;
- paginated loading/empty/error UI.

## NEXT — Stage 4 organization permissions UX

- permission preset editor;
- Owner/Admin/Manager/Teacher/Accountant presets;
- optional per-user capability overrides;
- assigned-groups-only scope where applicable;
- visible effective permissions;
- audited access changes;
- explicit access-removal UX on deactivation;
- keep last-owner protection.

## NEXT — Stage 5 organization onboarding

- guided organization setup;
- timezone/currency/locale;
- optional locations/rooms;
- first staff invite;
- first tariff;
- first group or individual-learning setup;
- setup checklist;
- no AeroKids-specific defaults in generic flows.

## NEXT — Stage 6 production communication

Outbox exists. Provider transport still depends on deployment credentials:
- choose SMTP/transactional provider;
- configure sender/domain;
- enable transport;
- verify invite/password-reset delivery;
- retry/dead-letter visibility;
- admin delivery status;
- raw one-time tokens removed after successful delivery.

## NEXT — Stage 7 monitoring, backups and DR

Application mechanisms exist; external operations remain:
- confirm managed DB backup policy;
- private backup destination and cadence;
- periodic restore drill;
- alert ownership for API downtime/deploy failure/DB failure/invariant failures;
- latency/5xx/saturation dashboard;
- rollback decision rules.

## NEXT — Stage 8 public intake migration

Only after private production acceptance:
- connect `aerokids.space` registration to CRM public intake;
- preserve honeypot/rate-limit/duplicate/sibling behavior;
- measure failures and retain rollback path.

## LATER

- payment-provider webhook layer with signature verification and unique event IDs before LiqPay/WayForPay;
- SaaS organization plans/limits/billing;
- MFA/passkeys/session management;
- teacher payroll;
- parent portal;
- homework/content;
- equipment/resource inventory;
- advanced recurrence only when real requirements justify it.

## Business rules that must never be lost

- CRM funnel status and learning lifecycle are separate.
- A student may learn without a group/location through individual lessons.
- Historical participation is determined by enrollment interval at lesson date.
- Schedule edits never rewrite completed history.
- Finalized lesson is the billing boundary; reopening is audited.
- Sold subscription price and behavior are snapshots.
- Financial history is charges + immutable transactions/adjustments, never one mutable balance.
- Organization-local timezone governs business dates.
- Tenant-owned references never cross organizations.
- Production never displays demo students as fallback.

## Release acceptance rule

A stage/slice is DONE only when:
1. code is merged to `crm-v1`;
2. CI is green on the merged commit;
3. affected Render API/frontend is live on that exact commit;
4. `/ready` is healthy;
5. Alembic is at repository head when schema changed;
6. production invariant audit has no critical findings for schema/business changes;
7. affected browser/API flows are smoke-tested.

## Continuation protocol

When context resets:
1. read this file and `roadmap.md`;
2. inspect current `crm-v1` head;
3. inspect merged PRs after the head recorded here;
4. inspect Render live commit for API and frontend;
5. mark already-completed work DONE instead of rebuilding it;
6. continue from the first unfinished Stage 2/next-stage item;
7. update this handoff whenever priorities or completion state materially change.
