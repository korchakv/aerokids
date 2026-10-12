# Ізольоване тестове середовище CRM

## Принцип

- Production залишається на `crm-v1`, адреса для роботи — `https://crm.aerokids.space`.
- Тестова гілка — `crm-staging`; вона ніколи не є джерелом production-сервісів.
- Тестовий Blueprint — `crm/render.staging.yaml` (у Render Dashboard вкажіть саме цей шлях).
- Тестова база `aerokids-crm-staging-db` уже створена окремо від Neon production. Blueprint не створює другу базу; його `DATABASE_URL` і `MIGRATION_DATABASE_URL` потрібно заповнити внутрішнім URL цієї staging бази через Render Dashboard. Не переносити в неї реальні дані учнів.
- Тестові frontend/API сервіси мають інші назви та адреси. На тесті створюються лише вигадані записи.
- Робочі фічі вносяться в окремих feature-гілках через PR. Спочатку PR у `crm-staging`; після приймального тесту відкривається PR тієї самої feature-гілки до `crm-v1`.
- На `crm-staging` CI запускається на кожен push, а Render Blueprint має `autoDeployTrigger: checksPass`. Тобто невдала CI-перевірка не повинна потрапити в тестовий деплой.
- На першому запуску Render створить порожню базу. У першому вікні CRM створіть тестову організацію та власника. `BOOTSTRAP_SECRET` задається в Render як секрет і не комітиться.

## Одноразове створення середовища

1. Гілка `crm-staging` від актуальної `crm-v1`, конфігурація `crm/render.staging.yaml` і запуск `crm-ci.yml` на push до `crm-staging` уже підготовлені. Перед продовженням перевірити, що CI зелений на останньому commit.
2. У Render Dashboard вибрати **New → Blueprint** і під’єднати `korchakv/aerokids`.
3. Для гілки Blueprint вибрати `crm-staging`. Для Blueprint file path вказати `crm/render.staging.yaml`, а не кореневий `render.yaml`.
4. Перевірити, що план створює лише `aerokids-crm-api-staging` і `aerokids-crm-staging`. Якщо показані production-сервіси або створення/підключення до Neon production — скасувати й виправити Blueprint.
5. Для `aerokids-crm-api-staging` встановити `DATABASE_URL` і `MIGRATION_DATABASE_URL` значенням **Internal Database URL** з картки `aerokids-crm-staging-db`. Обидві змінні мають вказувати на ту саму тестову базу; URL не вставляти в Git, PR чи чекліст.
6. Задати окремий випадковий `BOOTSTRAP_SECRET` не менше 32 символів у секретних змінних саме staging API. Render сам генерує `JWT_SECRET`.
7. Створити Blueprint та дочекатися `/ready` у staging API. Відкрити staging frontend і створити тестову організацію та обліковий запис власника.
8. Зберегти посилання на dashboard тестових сервісів у менеджері паролів. Пароль власника і bootstrap key не зберігати в репозиторії.

Staging PostgreSQL створено на free-плані у Frankfurt; поточний строк дії — до 11 листопада 2026 року. Він призначений лише для перевірок, може мати обмеження продуктивності й не є резервною копією production. Перед завершенням строку тестову базу можна скинути й створити заново. Дані тесту не повинні бути єдиним місцем зберігання реальних учнів.

## Цикл однієї фічі

1. Створити `crm/<коротка-назва>` від актуальної `crm-v1`.
2. Зробити одну фічу; додати автоматизовані тести для поведінки та регресій.
3. Відкрити PR до `crm-staging`. Перевірити, що всі сім CRM CI-перевірок пройшли.
4. Після зеленого CI злити PR у `crm-staging`. Дочекатися успішного Render deploy та здорового `/ready`.
5. Увійти до тестової CRM та пройти лише відповідні розділи чекліста `docs/test-plan-acceptance.md`, а також коротку регресію.
6. Якщо знайдено проблему — виправлення додати в ту саму feature-гілку, оновити PR у staging і повторити CI та ручний тест.
7. Коли ви підтвердили результат, відкрити PR тієї самої feature-гілки до `crm-v1`. Дочекатися семи перевірок і лише тоді злити в production.
8. Переконатися, що Render frontend та API розгорнули саме production commit, `/ready` працює, а перевірка даних не показує порушень.
9. Після успішного production deploy оновити `crm-staging` з `crm-v1`, щоб наступна фіча тестувалась на актуальній основі.

Тестування на спільному staging виконується послідовно: поки ви приймаєте одну зміну, не розгортати туди іншу. Це не дасть новому деплою змінити екран посеред тесту.

## Що перевірити при кожному staging deploy

- frontend сервіс: `aerokids-crm-staging`;
- API сервіс: `aerokids-crm-api-staging`;
- frontend використовує тільки staging API;
- API використовує тільки staging database;
- API `GET /ready` повертає успіх;
- у браузері немає критичних помилок або запитів до production API;
- SMTP вимкнений, робочі паролі й база не використовуються.

Ручний сценарій і очікувані результати: [`test-plan-acceptance.md`](test-plan-acceptance.md).
