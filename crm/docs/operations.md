# CRM production operations

## Health and readiness

- `GET /health` verifies that the API process responds.
- `GET /ready` verifies that the API can execute a database query.
- Both endpoints must remain side-effect free.
- Render health check uses `/ready`.

## Daily maintenance

The idempotent maintenance job is implemented in:

`python -m app.jobs.daily_maintenance`

The production HTTP trigger is:

`POST /internal/operations/daily-maintenance`

It requires the `X-Maintenance-Secret` header to exactly match `MAINTENANCE_SECRET`.

The endpoint:
- refuses to run if the secret is not configured;
- refuses to run in `READ_ONLY_MODE`;
- returns a non-2xx result if organization maintenance or email delivery is degraded;
- never exposes the configured secret;
- is intended for a server-side scheduler only.

The repository contains `.github/workflows/crm-maintenance.yml`. GitHub scheduled workflows execute only from the repository default branch, so the scheduler workflow must also exist on `main` even though the CRM application code is deployed from `crm-v1`.

Activation requires the same random 32+ character value in:
- Render API environment variable `MAINTENANCE_SECRET`;
- GitHub Actions repository secret `CRM_MAINTENANCE_SECRET`.

Do not place this value in source, docs, issue comments, workflow YAML or chat logs.

## What maintenance performs

For every organization:
- reconciles future recurring group sessions;
- runs subscription renewal / pause lifecycle;
- creates missing tariff-rule snapshots;
- records per-organization errors without silently skipping them.

Globally:
- removes stale auth/public-intake throttle rows;
- delivers pending transactional-email outbox items when email is enabled.

All operations are designed to be idempotent.

## Logging and request correlation

Application logs under the `schoolcrm.*` namespace are JSON-formatted.

Every HTTP request receives an `X-Request-Id`.
- an incoming request ID is trimmed and bounded to 128 characters;
- if absent, the API generates a UUID;
- the same ID is returned to the client and written to logs.

Production logging must never include:
- passwords;
- JWTs;
- reset/invite raw tokens;
- maintenance/bootstrap secrets;
- database URLs;
- full request bodies containing child/contact data.

## Incident checklist

When the CRM appears unhealthy:

1. Check Render deploy/event state for `aerokids-crm-api` and `aerokids-crm`.
2. Check `/health`, then `/ready`.
3. Find the failing request by `X-Request-Id` in Render logs.
4. Check recent API 5xx responses and server failure events.
5. Check Neon for long-running/stalled queries and locks.
6. If data writes should stop, set `READ_ONLY_MODE=true` on the API.
7. Run the read-only invariant auditor against production.
8. If the latest deploy introduced the failure, roll back to the last known-good Render deploy.
9. Do not run manual data-repair SQL until a backup/restore point exists and the exact repair has been reviewed.

## Database recovery

See `backup-restore.md`.

A backup is not considered proven until it has been restored into an isolated database and the invariant auditor passes there.

## Deploy acceptance checklist

A CRM deploy is considered production-complete only after:
- GitHub CI is green on the merged `crm-v1` commit;
- Render API reports that exact commit as live;
- Render frontend reports that exact commit as live;
- `/ready` is healthy;
- production Alembic head equals repository head;
- read-only production invariant audit shows no critical findings.
