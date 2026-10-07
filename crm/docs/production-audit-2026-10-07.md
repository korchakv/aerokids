# Production database audit — 2026-10-07

This document contains aggregate operational results only. No child, family or credential data is stored here.

## Target

- Neon project: `aerokids-crm-production`
- region: Frankfurt / AWS eu-central-1
- database: `neondb`
- primary branch: `production`

## State before Core Hardening production deploy

At audit time:
- repository `crm-v1` head: `c0f8ff24588a6e0a1995d28ba474a5f97c608522`;
- production Alembic head: `0021_deferred_leads`;
- Core Hardening migrations `0022`–`0025` were not yet present in production;
- Render still reported the previous application commit as live.

Therefore this audit intentionally used only read-only queries compatible with the old production schema.

## Aggregate data state

- organizations: 1
- students: 5
- groups: 2
- enrollments: 0
- lesson sessions: 36
- trial lessons: 2
- attendance rows: 0
- payments: 0
- subscriptions: 0
- staff records: 2
- active organization memberships: 2

## Invariant results

Zero findings:
- cross-tenant enrollment;
- cross-tenant group schedule;
- cross-tenant lesson;
- cross-tenant attendance;
- cross-tenant subscription;
- cross-tenant payment;
- cross-tenant group/staff assignment;
- inactive staff with active membership;
- Staff/Membership role drift;
- multiple primary contacts for one student;
- active enrollment attached to inactive student;
- duplicate active renewal children;
- lesson resource overlap detectable by the old schema;
- recurring group-schedule overlap detectable by the old schema.

Non-critical findings:
- 2 orphan contacts with no linked student;
- 1 overlap between two scheduled trial lessons at the same location/time under the legacy trial model.

No destructive cleanup was performed.

## Required post-deploy audit

After Render deploys the hardening commit and Alembic reaches `0025_subscription_rule_snapshots`:
1. rerun `python -m app.jobs.audit_invariants` against production read-only credentials where possible;
2. verify all new hardening tables exist;
3. verify the partial unique renewal index exists;
4. verify no critical findings;
5. review legacy orphan contacts and trial overlap through the CRM UI before any deletion or rescheduling.
