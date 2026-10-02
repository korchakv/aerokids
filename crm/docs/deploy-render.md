# Test deployment on Render

The repository now contains a root `render.yaml` Blueprint for a temporary CRM test environment.

It creates:

- `korchakv-aerokids-crm-api` — FastAPI backend;
- `korchakv-aerokids-crm` — React static frontend;
- `korchakv-aerokids-crm-db` — PostgreSQL 16.

## Deploy

1. Open Render.
2. Choose **New → Blueprint**.
3. Connect the GitHub repository `korchakv/aerokids`.
4. Select branch `crm-v1`.
5. Render reads `render.yaml`.
6. When prompted for `BOOTSTRAP_SECRET`, enter a private value with at least 16 characters and save it somewhere safe.
7. Deploy the Blueprint.
8. Open the frontend service URL.
9. On first launch, create the organization and owner. The **Ключ першого запуску** field is the same `BOOTSTRAP_SECRET`.

## Expected test URLs

- Frontend: `https://korchakv-aerokids-crm.onrender.com`
- API: `https://korchakv-aerokids-crm-api.onrender.com`
- API readiness: `https://korchakv-aerokids-crm-api.onrender.com/ready`

If Render changes either generated hostname, update:

- backend `CORS_ORIGINS`;
- frontend `VITE_API_URL`.

## Important limits of the free test environment

This setup is for testing, not production. The free Render PostgreSQL database expires after its free retention period and has no production-grade backups. Before using the CRM for real students or payments, move the database to a persistent paid plan and configure backups.

## First manual acceptance flow

After first login, verify this exact flow:

1. create a location;
2. create a manual lead;
3. set preferred location and available days/time;
4. schedule a trial lesson;
5. complete the trial;
6. move the child to **Очікує групу**;
7. form a group with a recurring schedule;
8. create a lesson;
9. mark attendance;
10. create a subscription plan;
11. create a student charge and mark it paid;
12. verify the audit history and reports.

Only after this flow is stable should the public AeroKiDS website form be switched from Formspree to the CRM public intake endpoint.
