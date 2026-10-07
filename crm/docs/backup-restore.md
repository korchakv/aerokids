# Backup, restore and disaster-recovery drill

A backup is not considered usable until it has been restored into an isolated database and the CRM integrity audit passes.

## Backup

Prefer the direct/unpooled PostgreSQL connection for `pg_dump`.

```bash
cd crm
DATABASE_URL_UNPOOLED='postgresql://...' ./scripts/backup-postgres.sh
```

The script:

1. creates a PostgreSQL custom-format dump;
2. does not print the connection string;
3. writes the file with restrictive filesystem permissions when supported;
4. runs `pg_restore --list` to verify the archive can be parsed.

Do not commit dump files to Git. Store them in a private, access-controlled backup destination.

## Restore drill

Create an isolated disposable PostgreSQL database or database branch. Never point the drill at production.

```bash
cd crm
RESTORE_DATABASE_URL='postgresql://isolated-test-db' \
  ./scripts/restore-drill.sh ./backups/schoolcrm-YYYYMMDDTHHMMSSZ.dump
```

The restore script refuses to proceed when `RESTORE_DATABASE_URL` exactly matches the source database URL available in the environment.

After restore it runs:

```bash
python -m app.jobs.audit_invariants
```

The drill is successful only when the restore completes and the invariant audit exits successfully.

## Recommended production policy

For the private beta:

- use the database provider's automatic snapshots / point-in-time recovery where available;
- keep an independent logical dump on a regular cadence;
- run a restore drill after meaningful schema changes and at least periodically during normal operation;
- document who can access backups;
- never copy production child/student data into an unsecured developer machine;
- use an isolated database or privacy-safe branch for restore testing.

## Before a schema deployment

1. Confirm CI migrations pass from an empty PostgreSQL schema.
2. Create/confirm a recent provider backup or snapshot.
3. Apply Alembic migrations using a direct PostgreSQL connection.
4. Run `python -m app.jobs.audit_invariants` against the migrated environment.
5. Verify `/ready` and the main sign-in/workspace smoke flow.

## Recovery sequence

If a release corrupts data or schema behavior:

1. put the API into `READ_ONLY_MODE=true` when possible;
2. preserve logs and note the exact deployment/migration revision;
3. create a new isolated database from the last known-good snapshot/dump;
4. run migrations only if the application revision requires them;
5. run the invariant audit;
6. validate authentication, one organization workspace, one group, one lesson and one payment history;
7. switch the application connection only after validation;
8. keep the failed database untouched until the incident is understood.

Do not perform destructive repair SQL directly on the only production copy when a restored branch/database can be investigated first.
