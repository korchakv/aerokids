# Production verification — 2026-10-09

Aggregate evidence only; no child, contact or credential data.

## Verified release

- Verified runtime release: `9d2fadd8655ee3ea79279996d56e8925ce5668b9`, contains Core Hardening `c0f8ff24588a6e0a1995d28ba474a5f97c608522`.
- Merged-commit CRM CI run `37894005931`: 7/7 successful jobs, including desktop/mobile test-stack E2E.
- Render autoDeploy/checksPass configured, but no deploy/event for the latest green head. Root cause is not exposed by available service events; do not claim a diagnosed webhook failure.
- Recovery copy: Neon branch `br-autumn-fire-b1psk2pr`, `pre-0026-recovery-2026-10-09`, created before rollout without compute. Snapshot creation hit the account snapshot limit; no existing snapshot was deleted.
- API deploy `dep-db491f142hec73ahfvjg`: live on `9d2fadd` at 07:00:15 UTC. Previous attempt failed port scanning despite Uvicorn binding 0.0.0.0:10000; one retry without code/config changes succeeded. No application exception or migration failure observed.
- Frontend deploy `dep-db48mvjbc2fs73b0rj4g`: live on `9d2fadd`.
- Startup logs show Alembic `0025` -> `0026_stage3_performance_indexes`; production alembic_version matches.
- `/ready`: HTTP 200, database ok, request ID returned.
- Authenticated production desktop smoke through secure sign-in: organization, dashboard, leads, students, groups, schedule, attendance, billing, staff and settings load. Creation forms checked without saving test records. Production mobile and mutation workflows remain unverified.
- PR #104 removes hardcoded initial lesson dates; current date verified in the live creation form.

## Read-only production database audit

Initial audit used read-only Neon SELECT queries because direct PostgreSQL network access from the execution environment is unavailable. After the scheduler fix, the full Python invariant auditor also ran through production maintenance: zero critical finding types, one warning type (the same resource overlap), two informational unlinked contacts.

- 207 catalog-derived FK checks: zero orphan references and zero cross-tenant references.
- Staff/member role drift, inactive staff access, linked active staff without access: zero.
- Duplicate phone contacts / primary contacts: zero.
- Capacity, enrollment intervals, history interval validity, duplicate lessons, renewal duplicates, missing tariff snapshots: zero findings.
- Finalization status, archived-student subscriptions, subscription-usage identity, pending/completed makeup, sent raw tokens: zero findings.
- Partial unique renewal index present.
- Two unlinked contacts remain (known legacy informational finding).
- One scheduling resource overlap remains (known legacy warning). No production records were modified to clear it.
- Current finance/attendance tables have no records: balance, reconciliation and refund behavior cannot be validated from production history alone.

Counts: organizations 1; students 8; groups 2; enrollments 0; payments 0; transactions 0; subscriptions 0; usage 0; individual lessons 0; attendance 0; finalizations 0; outbox 0.

## Scheduler defect

- Scheduled maintenance run `37753307344`, job `113231597336`, failed with HTTP 401 on 2026-10-08.
- Workflow exists on main and requests GitHub OIDC.
- Production requirements installed bare `PyJWT`, which omits the cryptography RSA backend needed to verify GitHub RS256 tokens.
- Reproduced in a clean environment: bare PyJWT 2.15.1 has no RS256 algorithm.
- Fix: use `PyJWT[crypto]` and test an actual RSA-signed GitHub identity plus rejection of an incorrectly signed identity. Keep issuer/audience/repository/ref/workflow restrictions unchanged.
- PR #103 merged and deployed after 7/7 green CI. Production rerun of run `37753307344`, attempt 2, job `113700881773`: success. Organization errors empty; maintenance and full invariant auditor completed.
- Maintenance response confirms transactional email disabled, sent/failed/pending all zero.

## Restore drill defect

- The restore script passed its connection URL as a positional archive argument, so a real pg_restore invocation would fail before restoration.
- Fix uses explicit --dbname, --exit-on-error and --single-transaction. Source identity is required; matching database URLs with different credentials/options and Neon pooled/direct aliases are refused.
- Add read-only Alembic head verification before invariant audit, plus real PostgreSQL CI dump/restore coverage and refusal/failure regressions. This CI evidence does not constitute a production restore drill.

## Remaining acceptance blockers

- Production mobile viewport and full mutation workflow smoke.
- SMTP environment/provider configuration and real delivery not verified; outbox is currently empty.
- No configured Neon snapshot schedule observed; retained history window is six hours and existing manual snapshot is dated October 6.
- Logical pg_dump/restore drill remains unperformed: direct database network access and PostgreSQL CLI tools unavailable here. Recovery branch is not a completed restore drill.
- Review existing resource overlap and unlinked contacts through authorized UI; do not delete/reschedule automatically.
- Stage 2 modularization is already closed in HANDOFF.md; continue Stage 3 after production acceptance.
