# Production verification — 2026-10-09

Aggregate evidence only; no child, contact or credential data.

## Verified release

- `crm-v1`: `71570277044297bb6a48e3393118c58f9b54fe2c`, contains Core Hardening `c0f8ff24588a6e0a1995d28ba474a5f97c608522` (40 commits ahead).
- Merged-commit CRM CI run `37884429902`: 7/7 successful jobs.
- Render autoDeploy/checksPass configured, but no deploy/event for the latest green head. Root cause is not exposed by available service events; do not claim a diagnosed webhook failure.
- Recovery copy: Neon branch `br-autumn-fire-b1psk2pr`, `pre-0026-recovery-2026-10-09`, created before rollout without compute. Snapshot creation hit the account snapshot limit; no existing snapshot was deleted.
- API deploy `dep-db4876lg1s2s738jg7a0`: live on `7157027`.
- Frontend deploy `dep-db48764s728c739ttqpg`: live on `7157027`.
- Startup logs show Alembic `0025` -> `0026_stage3_performance_indexes`; production alembic_version matches.
- `/ready`: HTTP 200, database ok, request ID returned.
- Browser renders login form without demo fallback. Authenticated workspace and mobile production scenarios remain unverified pending secure sign-in.

## Read-only production database audit

Used Neon SELECT queries because direct PostgreSQL network access from the execution environment is unavailable. The Python invariant auditor was not run against production; do not equate this SQL coverage with the full auditor.

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
- Production acceptance requires green CI, deployment and a successful scheduler rerun after the fix.

## Remaining acceptance blockers

- Secure production sign-in for desktop/mobile workflow smoke.
- SMTP environment/provider configuration and real delivery not verified; outbox is currently empty.
- No configured Neon snapshot schedule observed; retained history window is six hours and existing manual snapshot is dated October 6.
- Logical pg_dump/restore drill remains unperformed: direct database network access and PostgreSQL CLI tools unavailable here. Recovery branch is not a completed restore drill.
- Review existing resource overlap and unlinked contacts through authorized UI; do not delete/reschedule automatically.
- Stage 2 modularization is already closed in HANDOFF.md; continue Stage 3 after production acceptance.
