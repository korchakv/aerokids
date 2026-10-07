# CRM implementation status

Target branch: `crm-v1`

## Working end-to-end flows

- first-run organization + owner bootstrap;
- login with credential-bound JWT sessions;
- organization membership, strict production RBAC and per-staff capability overrides;
- synchronized staff profile / membership role and access lifecycle;
- staff invitations, invite acceptance and password-reset links;
- optional transactional-email outbox for invitations and password resets;
- website/public intake -> Contact + Student;
- lead status workflow and deferred follow-up;
- trial scheduling with location/room/staff conflict checks;
- waiting list;
- group formation, capacity-safe enrollment and transfer;
- repeated enrollment episodes with preserved enrollment history;
- active, paused and archived student lifecycle;
- students learning without a group through individual lessons;
- recurring group schedule with future-session reconciliation and history;
- optional rooms inside locations;
- group, trial and individual lesson resource conflict checks;
- read-only lesson-list GET endpoints;
- historical lesson-date rosters;
- attendance finalization / controlled reopen;
- make-up reconciliation;
- subscription plans and frozen per-subscription tariff behavior rules;
- student subscriptions, partial payments, immutable payment ledger, refunds and adjustments;
- safe mid-period tariff change;
- idempotent automatic renewal for group and individual learners;
- organization-local dates for hardened renewal/reminder/pause rules;
- payment reminders;
- staff, locations, rooms and group assignments;
- tenant-scoped reports;
- organization timezone / currency / locale settings;
- preferred student location and structured weekly availability;
- schedule compatibility hints while forming groups;
- audit history with authenticated actor identity;
- duplicate-intake protection and international E.164-style phone support;
- privacy export, retention candidate listing and owner-controlled anonymization;
- read-only database invariant audit;
- backup and isolated restore-drill scripts;
- request IDs and structured request completion/error logs.

## Roles and permissions

Production uses `STRICT_RBAC=true`.

- owner — full organization access;
- admin — operations, finance, staff, settings, reports and teaching;
- manager — leads, students, groups, schedule, attendance, reports and teaching;
- teacher — teaching/attendance with assigned-group scope by default;
- accountant — finance and reports.

Per-staff capability overrides can broaden or restrict named capabilities. `OrganizationMembership` is the source of truth for organization access. Linked Staff role/active changes synchronize to Membership and are audited.

## Data source

When `VITE_API_URL` is configured, the frontend loads real organization data from FastAPI.

Production fails closed when the API URL is missing. Demo data is available only when `VITE_DEMO_MODE=true` is explicitly enabled.

## Production baseline

- PostgreSQL;
- Alembic migrations;
- JWT secret from environment;
- credential-bound JWT invalidation after password change;
- 120-minute production access-token configuration;
- authentication required;
- strict RBAC enabled;
- explicit HTTPS CORS origins;
- request IDs and security headers;
- backend and frontend Dockerfiles;
- Docker Compose stack for local full-system testing;
- invariant-audit job;
- idempotent daily-maintenance job;
- backup/restore-drill scripts;
- optional SMTP transactional-email delivery through a persistent outbox.

## CI baseline

CRM CI verifies:

- Python module compilation;
- backend tests on SQLite and PostgreSQL;
- Alembic migrations from an empty schema;
- frontend TypeScript/Vite build;
- backend and frontend Docker builds;
- full-stack API smoke flow;
- read-only invariant audit against the smoke database;
- Playwright desktop and iPhone-size browser smoke flows;
- Python dependency audit and Bandit;
- npm high-severity dependency audit;
- git-history secret scan.

## Deployment-side configuration still required

These are intentionally not hard-coded into the repository:

1. a production database connection and provider backup policy;
2. a scheduler that invokes `python -m app.jobs.daily_maintenance` when unattended daily execution is required;
3. SMTP credentials plus `TRANSACTIONAL_EMAIL_ENABLED=true` when email delivery is enabled;
4. a private backup destination and periodic restore drill;
5. production monitoring/alert ownership around Render/database health.

The application mechanisms are present; provider credentials and paid/free scheduler choice remain deployment configuration.

## Public website integration

Keep the AeroKiDS public website intake migration separate from core hardening. The CRM public intake endpoint is protected by honeypot and rate limits, but the public website should be switched only after the hardened private-beta deployment is verified.

Detailed invariants: `docs/core-hardening.md`.
Backup/recovery runbook: `docs/backup-restore.md`.
