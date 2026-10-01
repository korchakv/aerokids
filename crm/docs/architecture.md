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

Майбутній endpoint:
`POST /public/intake/{organization_slug}`

Він має:
1. rate limiting / anti-spam;
2. нормалізувати телефон;
3. знайти або створити Contact;
4. створити Student;
5. зв'язати StudentContact;
6. поставити `crm_status=new`;
7. записати source=website;
8. створити audit/event запис.

## Next technical milestone

Alembic + tenant-scoped CRUD + tests.
