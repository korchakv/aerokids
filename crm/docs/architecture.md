# Architecture v0.1

## Product boundary

CRM — універсальний продукт для шкіл та гуртків. AeroKiDS є demo/first tenant, а не окремою версією коду.

## Tenant model

`Organization` — tenant boundary.

Кожен запис, що належить бізнесу, має `organization_id`. API не приймає довільний organization id як достатній доказ доступу: після появи auth organization scope має братися з authenticated membership.

## CRM funnel without Lead entity

Ми не створюємо окремий Lead.

Після заявки створюються:
- Contact
- Student
- StudentContact

У Student окремо зберігаються:
- `crm_status` — етап продажу/комунікації;
- `student_status` — фактичний статус учня.

Це не дає змішувати "очікує групу" з "активний/пауза/архів".

## Group formation

Waiting list у MVP може бути запитом по `Student.crm_status = waiting_for_group` з фільтрами:
- age
- level
- location
- availability (додамо окремо)

Пізніше система може пропонувати кандидатів у групу, але автоматичне формування не повинно бути жорстким правилом.

## Integration with AeroKiDS site

Поточний Formspree endpoint залишаємо до появи захищеного public intake endpoint.

Public endpoint:
`POST /public/intake/{organization_slug}`

Він уже:
1. має DB-backed rate limiting окремо за IP та нормалізованим телефоном;
2. підтримує honeypot-поле `website` для форми;
3. нормалізує українські скорочені та явні міжнародні номери;
4. знаходить або створює Contact;
5. не створює дубль тієї самої дитини при повторній заявці;
6. створює/зв'язує Student + StudentContact;
7. ставить `crm_status=new` для нової дитини;
8. записує source та audit/event.

При підключенні сайту поле `website` треба додати як приховане й залишати порожнім для реального користувача.

## Next technical milestone

Alembic + tenant-scoped CRUD + tests.
