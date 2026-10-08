# CRM canonical continuation roadmap

Last updated: 2026-10-08
Target branch: `crm-v1`
Latest Stage 2 code baseline before this documentation PR: `749bb89e6b9be99695a8a5b59ce5220178e3a7d0`
Last confirmed Render live commit before the next release deployment: `c771cb43a25b0c38da8270667d0b7c191173b4c5`

This file and `HANDOFF.md` are the canonical continuation source after chat/context resets. Do not restart the CRM analysis from zero.

## Product contract

The CRM is a generic SaaS-ready product for schools, clubs and studios. AeroKids is the first tenant, not a product fork.

Core invariants:
- Organization is the tenant boundary;
- OrganizationMembership is authorization truth; Staff is the worker profile;
- teachers are assigned-group scoped by default;
- tenant-owned foreign keys never cross organizations;
- GET endpoints do not mutate business data;
- historical rosters/schedules/finances are reproducible;
- finalized lesson is the attendance/billing boundary;
- sold subscription price and behavior are immutable snapshots;
- business dates use organization timezone;
- production never falls back to demo data.

## DONE — Core Hardening

Reference: PR #45.

Completed:
- strict RBAC, access revocation, owner protection;
- credential-bound JWT invalidation;
- tenant validation;
- Room and resource conflict model;
- recurring schedule reconciliation/history;
- enrollment episodes/historical roster;
- concurrency-safe enrollment;
- individual lessons;
- trial conflicts;
- group archive lifecycle;
- actual lesson resource assignments;
- attendance finalize/reopen and billing/make-up reconciliation;
- renewal idempotency;
- subscription tariff-rule snapshots;
- organization-local financial lifecycle;
- privacy export/anonymization;
- invariant auditor;
- backup/restore scripts;
- production fail-closed safeguards;
- full SQLite/PostgreSQL/Docker/security/browser CI.

## DONE — Production operations foundation

References: PR #46, PR #47.

Completed:
- Render deployment model;
- structured JSON logs and request IDs;
- `/health`, `/ready`;
- idempotent daily maintenance endpoint;
- GitHub Actions scheduled maintenance;
- GitHub OIDC authentication without shared maintenance secret;
- invariant audit on maintenance;
- failure on critical invariants;
- incident/rollback docs.

## IN PROGRESS — Stage 2: maintainability and UI architecture

Goal: reduce regression risk before adding commercial SaaS features.

### Completed Stage 2 slices

Frontend:
- #48 modular frontend foundation;
- #49 domain projection models/adapters;
- #50 shell/navigation/availability/matching helpers;
- #52 Staff and Locations workspace views;
- #55 domain API façades;
- #63 Settings workspace;
- #65 Reports workspace;
- #66 Students workspace + student drawer;
- #69 Groups + waiting-candidates workspace.

Backend:
- #51 staff/membership service decomposition;
- #53 audit service;
- #54 location service;
- #57 reporting service;
- #59 organization service;
- #60 student service;
- #64 contact service;
- #67 trial lesson service;
- #68 core group CRUD service.

Every slice above was merged only after full CI; moved UI retains desktop/mobile Playwright coverage.

### Still required to complete Stage 2

Frontend:
1. Schedule workspace.
2. Attendance / lesson journal workspace.
3. Billing workspace and payment/subscription dialogs.
4. Group detail drawer and group create/edit dialogs.
5. Dashboard.
6. Remaining Leads detail/forms/shared modals.
7. Continue reducing direct `api.ts` compatibility imports until feature façades own domain calls.

Backend:
1. scheduling service;
2. attendance service;
3. billing service;
4. lead/intake service;
5. enrollment compatibility cleanup;
6. remove obsolete compatibility implementations after all callers move.

Acceptance for Stage 2:
- large orchestration files no longer contain authoritative domain business logic;
- no duplicate authoritative implementations remain;
- full CI/E2E remains green;
- stable Stage 2 head is live on Render before marking the stage done.

## NEXT — Stage 3: scale and performance

Required:
- actual server-side pagination for large leads/students/groups/payments/audit lists;
- server-side search/filter/sort;
- stable pagination contract;
- indexes validated against query plans;
- remove N+1 group/student detail paths;
- query-count/performance regression tests;
- bounded report queries;
- loading/empty/error states for paginated views.

Do not rely on loading every student into the browser for large tenants.

## NEXT — Stage 4: permissions UX

Backend capabilities already exist. Product UX still needs:
- permission preset editor;
- Owner/Admin/Manager/Teacher/Accountant presets;
- optional per-user overrides;
- assigned-groups-only scope;
- effective permissions explanation;
- complete audit UX for access changes;
- explicit warning that staff deactivation removes login access;
- last-owner protection exposed clearly in UI.

## NEXT — Stage 5: organization onboarding

Required:
- guided organization creation;
- name/timezone/currency/locale;
- optional locations;
- invite first staff;
- first tariff;
- first group or individual-learning setup;
- setup completeness checklist;
- generic defaults with no AeroKids assumptions.

## NEXT — Stage 6: production communication

Application outbox already exists.

Required:
- choose SMTP/transactional provider;
- configure sender/domain;
- enable production delivery;
- test invitation and password-reset deliverability;
- retry/dead-letter visibility;
- admin delivery status;
- raw one-time token removed after successful send.

Later messaging channels must use provider-neutral jobs.

## NEXT — Stage 7: monitoring, backups and disaster recovery

Application mechanisms exist; external operations remain:
- managed DB backup policy confirmed;
- private external backup destination;
- scheduled backup cadence;
- periodic automated restore drill;
- alert ownership for downtime, deploy failure, DB availability and critical invariant failure;
- latency / 5xx / saturation monitoring;
- documented rollback decision rules.

## NEXT — Stage 8: public website intake migration

Only after private production acceptance:
- point `aerokids.space` registration to CRM public intake;
- preserve honeypot/rate limiting;
- verify repeat/sibling submissions;
- monitor failures;
- keep temporary rollback transport during initial rollout.

## LATER — Stage 9: payment provider

Preserve immutable ledger. Add provider-specific attempts/events with:
- signature verification;
- unique provider event/transaction IDs;
- webhook idempotency;
- browser redirect never treated as proof of payment;
- manual/provider payments reconciled into the same transaction ledger.

## LATER — Stage 10: commercial SaaS controls

After operational stability:
- plan/feature limits;
- usage metering;
- tenant billing/trial;
- suspend/reactivate tenant;
- data export before closure;
- audited support tooling if needed;
- privacy/legal/retention commitments.

## Deferred, not forgotten

- MFA/passkeys;
- richer reporting;
- teacher payroll;
- homework/content;
- equipment inventory/resource planning;
- advanced recurrence;
- parent portal;
- native mobile app.

## Immediate release task

The repository is ahead of the last confirmed production Render commit.

Before considering the current Stage 2 batch released:
1. finish/merge this documentation update;
2. wait for green CI on the exact merged `crm-v1` head;
3. confirm whether Render auto-deployed that SHA;
4. if not, trigger both API and frontend deploys manually;
5. require both to report the exact same SHA as live;
6. verify `/ready`;
7. confirm the latest production maintenance/invariant run has no critical findings.

## Release acceptance rule

A stage/batch is not DONE until:
1. code is merged to `crm-v1`;
2. CI is green on the merged commit;
3. Render API and frontend are live on the exact affected commit;
4. `/ready` is healthy;
5. Alembic is current when schema changed;
6. production invariant audit has no critical findings;
7. affected API/browser flows are smoke-tested.

## Continuation protocol

When work resumes:
1. read `HANDOFF.md` and this file;
2. inspect current `crm-v1` head;
3. inspect recent merged/open PRs after the recorded baseline;
4. compare Render live SHA with repository SHA;
5. do not recreate completed work;
6. continue the first unfinished Stage 2 item;
7. update these files whenever the plan materially changes.
