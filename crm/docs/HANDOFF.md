# CRM canonical handoff

Updated: 2026-10-08
Canonical product branch: `crm-v1`
Current Stage 2 repository head when this handoff was prepared: `749bb89e6b9be99695a8a5b59ce5220178e3a7d0`
Last confirmed Render live commit before the next deployment: `c771cb43a25b0c38da8270667d0b7c191173b4c5`

This is the canonical continuation point for future ChatGPT/project sessions. Read this file together with `roadmap.md`, `architecture.md`, `core-hardening.md`, `operations.md`, `status.md`, and `backup-restore.md`. Do not restart the CRM analysis from zero and do not rebuild items already marked complete.

## Product direction

The CRM is a generic SaaS-oriented product for schools, clubs and learning organizations. AeroKids is the first tenant, not a separate fork. Keep the system a modular monolith and preserve support for multiple organizations, locations, rooms, staff members, teachers, groups and individual learners.

## Completed foundation

### Core Hardening — complete

PR #45 completed the core-hardening phase. The implemented invariants include:
- strict production RBAC and assigned-group teacher scope;
- synchronized Staff / User / OrganizationMembership access state;
- last-owner protection;
- credential-bound JWT invalidation and shorter production token lifetime;
- tenant-scoped validation across CRM-owned relations;
- Room and lesson resource assignments;
- trial/group/teacher/room conflict checks;
- recurring schedule reconciliation and schedule history;
- no business-data writes from lesson-session GET;
- historical enrollment episodes and lesson-date rosters;
- pause/resume/archive and group lifecycle controls;
- individual lessons without fake one-person groups;
- lesson finalization/reopen and deterministic attendance/billing reconciliation;
- make-up reconciliation;
- idempotent/concurrency-safe renewal and enrollment;
- organization-local business dates;
- tariff behavior snapshots per sold subscription;
- immutable payment transaction model;
- privacy export/anonymization;
- transactional notification outbox;
- request IDs and forwarded-IP hardening;
- explicit production demo-data guard;
- pagination/search foundation;
- database invariant auditor;
- backup and restore-drill scripts;
- SQLite/PostgreSQL/API/Docker/security/secret/browser CI.

### Production operations — complete

PR #46 and #47 established:
- Render API/frontend deployment path;
- structured JSON logs and request IDs;
- `/health` and `/ready`;
- idempotent daily maintenance;
- GitHub Actions scheduled maintenance;
- GitHub Actions OIDC authentication without a shared cron secret;
- invariant audit after maintenance;
- failure of maintenance on critical invariant findings;
- incident/rollback documentation.

The last production-operations baseline was `172124a...`.

## Stage 2 maintainability progress

Merged PRs:
- #48 — modular frontend foundation;
- #49 — domain UI projection models and adapters;
- #50 — navigation, availability, schedule helpers and group candidate matching helpers;
- #51 — backend decomposition started with staff/membership;
- #52 — Staff and Locations workspace views;
- #53 — audit service;
- #54 — location service;
- #55 — frontend API façades by domain;
- #57 — reporting service;
- #59 — organization service;
- #60 — student service;
- #63 — Settings workspace view;
- #64 — contact service;
- #65 — Reports workspace view;
- #66 — Students workspace and student drawer;
- #67 — trial lesson service;
- #68 — core group CRUD service;
- #69 — Groups / waiting-candidates workspace view.

All merged slices followed the release rule: dedicated PR, full CI, desktop/mobile browser coverage where UI moved, then merge.

At this handoff:
- legacy `crm.py` has already been materially reduced but still contains leads/intake, enrollment compatibility flows, scheduling, attendance and substantial billing logic;
- `App.tsx` is reduced but still owns Dashboard, Leads orchestration/forms, Schedule, Attendance, Billing, group detail/modals and several cross-feature dialogs;
- domain API façades exist, but `api.ts` compatibility ownership should continue shrinking gradually.

## Exact next Stage 2 work

Continue in small behavior-preserving PRs from the latest `crm-v1`.

Recommended next order:
1. extract Schedule workspace from `App.tsx`;
2. extract Attendance workspace / lesson journal;
3. extract Billing workspace and payment/subscription dialogs;
4. extract group detail drawer and group creation/edit dialogs;
5. extract Dashboard;
6. finish Leads forms/detail orchestration after shared modals are clearer;
7. continue backend decomposition:
   - scheduling service;
   - attendance service;
   - billing service;
   - lead/intake service;
   - enrollment compatibility cleanup;
8. once callers are moved, remove dead compatibility code instead of keeping two authoritative implementations.

Do not move business rules into React components while extracting views. App may temporarily own state/callbacks until feature controllers/hooks are introduced safely.

## Immediate production task

GitHub Stage 2 has advanced beyond the last confirmed Render live commit.

Before calling the current Stage 2 batch released:
1. obtain the exact latest `crm-v1` SHA after the current documentation merge;
2. require green CI on that merged SHA;
3. check Render API and frontend deployments;
4. if checksPass auto-deploy still does not pick up the SHA, trigger both Render services manually;
5. verify both services report that exact SHA as live;
6. verify API `/ready`;
7. verify the production invariant audit / scheduled maintenance has no critical findings.

Render resources:
- workspace: `tea-d880uv3bc2fs73efjob0` (Maria's workspace);
- API service: `srv-davkqbbncjis73eov5h0` / `aerokids-crm-api`;
- frontend service: `srv-davkpvu0tbcc73ej5big` / `aerokids-crm`;
- both deploy from `crm-v1`;
- unrelated `malyarnyi-bot` must not be touched.

## Remaining roadmap after Stage 2

Stage 3 — scale/performance:
- true server-side pagination/filtering/sorting for large lists;
- remove N+1 detail paths;
- query-count/performance regression tests;
- bounded report queries and loading/error states.

Stage 4 — permissions UX:
- permission presets and per-user overrides;
- assigned-groups scope controls;
- effective-permission explanations;
- access-change audit UX.

Stage 5 — generic tenant onboarding:
- organization basics;
- optional locations;
- first staff invite;
- first tariff;
- first group/individual-learning setup;
- setup checklist;
- no AeroKids-specific defaults.

Stage 6 — production communication:
- choose/configure transactional email provider;
- sender/domain setup;
- outbox retry/dead-letter visibility;
- invite/password-reset delivery verification.

Stage 7 — monitoring/backups/DR:
- external managed backup policy and private destination;
- scheduled backup cadence;
- recurring restore drill;
- downtime/deploy/DB/invariant alerts;
- latency/5xx/saturation monitoring;
- rollback decision rules.

Stage 8 — public website intake migration.
Stage 9 — payment provider with signed/idempotent webhooks.
Stage 10 — commercial SaaS controls and tenant billing.

## Business rules that must never regress

- CRM funnel state and learning lifecycle are separate.
- Individual students may learn without a group/location.
- Historical participation uses enrollment at the lesson date, not current membership.
- Recurring schedule edits never silently rewrite completed history.
- Finalized lesson is the billing boundary; reopen is audited.
- Tariff price/rules are snapshots for sold subscriptions.
- Financial history is charge + immutable transactions/adjustments, not a mutable balance field.
- Organization-local timezone governs business dates.
- Tenant-owned references never cross organizations.
- Production fails closed if required API/auth configuration is absent.
- Demo data must never appear as a production fallback.
- GET endpoints remain side-effect free.

## Continuation protocol

Every future CRM session must:
1. read `crm/docs/HANDOFF.md` and `crm/docs/roadmap.md`;
2. read current `crm-v1` head and recent merged/open PRs;
3. compare Render live commit with repository head;
4. mark completed work as done rather than recreating it;
5. continue the first unfinished roadmap item;
6. use dedicated branches/PRs;
7. require full CI green before merge;
8. verify exact live deployment for release-sensitive batches;
9. update these handoff documents whenever the roadmap materially changes.
