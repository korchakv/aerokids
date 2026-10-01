# School CRM backend

## Швидкий запуск

У каталозі `crm/backend`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

За замовчуванням development використовує SQLite.

Для PostgreSQL:

```bash
docker compose -f ../docker-compose.yml up -d
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Swagger: `/docs`.

## Тимчасовий tenant scope

Поки немає авторизації, CRM endpoints використовують заголовок:

`X-Organization-Id: <uuid>`

Це лише development-механізм. У production organization буде визначатися через authenticated membership.

## Public intake

`POST /public/intake/{organization_slug}`

Це майбутня точка входу для форми сайту. Поки сайт AeroKiDS лишається на Formspree.

## Тести

```bash
pytest
```
