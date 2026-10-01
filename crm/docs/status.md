# CRM implementation status

Branch: `crm-v1`

## Working end-to-end flows

- first-run organization + owner bootstrap;
- login with JWT session;
- organization membership and role checks;
- staff invitations and invite acceptance;
- website/public intake -> Contact + Student;
- lead status workflow;
- trial scheduling and completion;
- waiting list;
- group formation and enrollment;
- active student registry and transfer between groups;
- recurring group schedule;
- lesson sessions;
- attendance journal;
- subscription plans;
- student subscriptions;
- payments and payment summary;
- staff, locations and group assignments;
- tenant-scoped reports;
- organization timezone / currency / locale settings;
- preferred student location and structured weekly availability;
- schedule compatibility hints while forming groups;
- audit history with authenticated actor identity;
- duplicate-intake protection and international E.164-style phone support.

## Roles

- owner — full organization access;
- admin — operational administration;
- manager — leads/students/groups/schedule/attendance/reports;
- teacher — only assigned groups, their students, lessons and attendance;
- accountant — finance and reports.

Role checks are enforced on the API, not only hidden in the frontend.

## Data source

When `VITE_API_URL` is configured, the frontend loads real organization data from FastAPI.
Without it, the React UI keeps demo data for visual development.

## Production baseline

- PostgreSQL;
- Alembic migrations;
- JWT secret from environment;
- auth required;
- explicit CORS origins;
- backend and frontend Dockerfiles;
- Docker Compose stack for local full-system testing.

## Before public beta

1. Deploy a private beta stack with managed PostgreSQL and HTTPS.
2. Add password recovery / transactional email delivery.
3. Add date filters and pagination where lists can grow large.
4. Add backup/restore and production observability.
5. Move AeroKiDS website form from Formspree to the public intake endpoint only after the private beta is stable.

CI now runs the full backend test suite on both SQLite and PostgreSQL, verifies Alembic migrations, builds the React frontend, and validates both Docker images.
