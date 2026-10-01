# School CRM

Універсальна multi-tenant CRM для шкіл, гуртків і навчальних центрів. AeroKiDS — перша організація, на якій перевіряємо продукт.

## MVP 1

Перший наскрізний сценарій:

**заявка з сайту → дитина/контакт → пробне заняття → очікує групу → група → активний учень**

Базові сутності закладаються одразу з підтримкою кількох організацій, локацій і працівників.

## Архітектурні принципи

- modular monolith, без мікросервісів на старті;
- PostgreSQL у production, SQLite дозволено лише для швидкого локального запуску;
- кожна бізнес-сутність належить до `organization_id`;
- tenant isolation обов'язково перевіряється тестами;
- `Contact`, а не жорстко `Parent`;
- `Staff`, а не лише `Teacher`;
- навчання не прив'язане до фіксованого "курсу";
- групи, enrollment і розклад — окремі сутності;
- платежі, SaaS billing, white-label та зовнішні месенджери — не в MVP 1.

## Структура

- `backend/` — FastAPI + SQLAlchemy;
- `frontend/` — React + TypeScript;
- `docs/` — продуктова та технічна документація;
- `CODEX.md` — інструкція для Codex.

## Перший реліз

1. Organizations / Locations / Staff.
2. Contacts / Students.
3. Trial lessons.
4. Waiting list + Groups.
5. Enrollment.
6. Простий Dashboard.

Сайт AeroKiDS зараз використовує Formspree. Після стабілізації API форма сайту буде відправляти заявку безпосередньо в CRM.
