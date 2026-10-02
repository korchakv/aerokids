# School CRM

Універсальна multi-tenant CRM для шкіл, гуртків і навчальних центрів. AeroKiDS — перша організація, на якій перевіряється продукт, але домен і база не прив'язані лише до AeroKiDS.

## Поточний наскрізний сценарій

**заявка → контакт/дитина → пробне → очікує групу → група → активний учень → розклад → заняття → відвідування → абонемент → оплата**

Додатково вже є працівники, ролі, локації, запрошення в CRM та звіти.

## Архітектура

- modular monolith;
- FastAPI + SQLAlchemy + Alembic;
- PostgreSQL у production, SQLite тільки для development/tests;
- React + TypeScript frontend;
- `Organization` є tenant boundary;
- tenant isolation перевіряється тестами;
- роль і membership перевіряються backend API;
- `Contact`, а не жорстко `Parent`;
- `Staff`, а не лише `Teacher`;
- CRM status та student status розділені;
- довготривале навчання моделюється через enrollment, а не фіксований course.

## Каталоги

- `backend/` — FastAPI API;
- `frontend/` — React UI;
- `docs/` — архітектура і статус;
- `CODEX.md` — правила для Codex;
- `docker-compose.yml` — локальний full-stack PostgreSQL + API + frontend.

## Локальний full-stack

З каталогу `crm/`:

```bash
docker compose up --build
```

Після запуску:
- CRM: `http://localhost:8080`
- API docs: `http://localhost:8000/docs`

На чистій базі CRM сама покаже перший запуск для створення організації та власника.

## Важливо

Публічний сайт AeroKiDS поки не переводимо з Formspree на CRM до окремого етапу стабілізації та deployment.

Детальний поточний стан: `docs/status.md`.


## Тестове розгортання

Для окремого тестового середовища підготовлено Render Blueprint у корені репозиторію: `render.yaml`.

Покрокова інструкція: `docs/deploy-render.md`.
