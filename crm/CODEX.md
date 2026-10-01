# Codex working brief — School CRM

Працюй тільки в каталозі `crm/` і не змінюй публічний сайт AeroKiDS без окремого запиту.

## Product goal

Побудувати базову SaaS CRM, придатну не лише для AeroKiDS, а для різних шкіл та гуртків із багатьма працівниками й локаціями.

## Non-negotiable architecture

1. Multi-tenant from day one.
2. `organization_id` на всіх tenant-owned бізнес-таблицях.
3. Жоден query не повинен повертати дані іншої organization.
4. `Contact` замість `Parent`.
5. `Staff` замість `Teacher`.
6. Не створювати окрему сутність Lead. Перший контакт створює/оновлює Contact + Student, а CRM-етап зберігається окремим статусом.
7. Не змішувати CRM status та academic/student status.
8. Long-term enrollment: не моделювати дитину як "курс на N місяців".
9. Modular monolith. Не додавати мікросервіси.
10. Не додавати Stripe, SaaS billing, white-label, Telegram/Viber інтеграції або superadmin у MVP 1.

## Initial domain

- Organization
- Location
- User
- Staff
- OrganizationMembership
- StaffLocation
- Contact
- Student
- StudentContact
- TrialLesson
- Group
- GroupStaff
- Enrollment
- StudentSubscription (пізніше в MVP 2)
- Attendance (пізніше в MVP 2)
- Payment (пізніше в MVP 2)

## AeroKiDS assumptions for seed/demo only

- 6–8 дітей у групі;
- групи формуються з урахуванням віку/рівня;
- заняття приблизно 60 хвилин;
- 2 рази на тиждень;
- пробне заняття безкоштовне;
- після пробного дитина може перейти у waiting-for-group.

Не хардкодити ці значення як правила платформи.

## First engineering tasks

1. Довести backend skeleton до запуску.
2. Налаштувати Alembic.
3. Додати SQLAlchemy 2.x models для MVP 1.
4. Додати Pydantic schemas.
5. Реалізувати API:
   - GET /health
   - POST/GET /organizations
   - POST/GET /locations
   - POST/GET /contacts
   - POST/GET /students
   - POST/GET /trial-lessons
   - POST/GET /groups
   - POST /enrollments
6. Додати tenant-scoped repository/service layer.
7. Додати тести, включно з cross-tenant isolation.
8. Після API — зібрати перший React dashboard.

## Coding rules

- Type hints everywhere.
- Keep routers thin; business logic in services.
- Explicit enums for statuses.
- UUID primary keys.
- UTC timestamps in DB.
- No secrets committed.
- English code identifiers; Ukrainian UI copy is allowed.
- Small cohesive commits.
