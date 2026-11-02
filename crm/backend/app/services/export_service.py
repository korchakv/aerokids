from __future__ import annotations

from io import BytesIO
from uuid import UUID

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    Contact, Enrollment, EnrollmentStatus, Group, GroupSchedule, LeadComment,
    Payment, Student, StudentContact, StudentStatus, StudentSubscription,
    SubscriptionPlan, TrialLesson, User,
)

WEEKDAYS = ("Понеділок", "Вівторок", "Середа", "Четвер", "П’ятниця", "Субота", "Неділя")
LABELS = {
    "new": "Нова заявка", "contacted": "Зв’язалися", "trial_scheduled": "Запис на пробне",
    "trial_completed": "Після пробного", "waiting_for_group": "Очікує групу",
    "enrolled": "У групі", "no_response": "Немає відповіді", "declined": "Відмова",
    "not_relevant": "Неактуально", "prospect": "Потенційний", "active": "Активний",
    "paused": "Призупинений", "archived": "Архівний", "scheduled": "Заплановано",
    "completed": "Проведено", "no_show": "Не прийшов", "cancelled": "Скасовано",
    "pending": "Очікує оплати", "paid": "Оплачено", "refunded": "Повернено",
    "finished": "Завершено",
}

def value(item):
    if item is None:
        return ""
    if hasattr(item, "value"):
        return LABELS.get(item.value, item.value)
    if hasattr(item, "isoformat"):
        return item.isoformat(sep=" ") if hasattr(item, "hour") else item.isoformat()
    return item

def make_sheet(book, title, headers, rows):
    sheet = book.create_sheet(title)
    sheet.append(headers)
    for row in rows:
        sheet.append([value(item) for item in row])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 32
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="263746")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for column in sheet.columns:
        letter = get_column_letter(column[0].column)
        width = max(12, min(42, max((len(str(cell.value or "")) for cell in column[:100]), default=10) + 2))
        sheet.column_dimensions[letter].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    return sheet

def build_students_export(db: Session, org_id: UUID) -> bytes:
    students = list(db.scalars(select(Student).where(Student.organization_id == org_id)))
    groups = {row.id: row for row in db.scalars(select(Group).where(Group.organization_id == org_id))}
    enrollments = list(db.scalars(select(Enrollment).where(Enrollment.organization_id == org_id)))
    active_enrollments = {}
    for enrollment in enrollments:
        if enrollment.status in (EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED):
            active_enrollments.setdefault(enrollment.student_id, []).append(enrollment)

    schedule_by_group = {}
    for slot in db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id, GroupSchedule.is_active.is_(True)
    )):
        day = WEEKDAYS[slot.weekday] if 0 <= slot.weekday < len(WEEKDAYS) else str(slot.weekday)
        schedule_by_group.setdefault(slot.group_id, []).append(
            f"{day} {slot.start_time.strftime('%H:%M')} ({slot.duration_minutes} хв)"
        )

    links = list(db.scalars(select(StudentContact).where(StudentContact.organization_id == org_id)))
    contacts = {c.id: c for c in db.scalars(select(Contact).where(Contact.organization_id == org_id))}
    contacts_by_student = {}
    for link in links:
        contact = contacts.get(link.contact_id)
        if contact:
            contacts_by_student.setdefault(link.student_id, []).append((link, contact))
    for rows in contacts_by_student.values():
        rows.sort(key=lambda pair: not pair[0].is_primary)

    comments = list(db.scalars(select(LeadComment).where(
        LeadComment.organization_id == org_id
    ).order_by(LeadComment.created_at)))
    users = {u.id: u for u in db.scalars(select(User))}
    comments_by_student = {}
    for comment in comments:
        comments_by_student.setdefault(comment.student_id, []).append(comment)

    trials = list(db.scalars(select(TrialLesson).where(TrialLesson.organization_id == org_id)))
    trials_by_student = {}
    for trial in trials:
        trials_by_student.setdefault(trial.student_id, []).append(trial)

    subscriptions = list(db.scalars(select(StudentSubscription).where(StudentSubscription.organization_id == org_id)))
    plans = {p.id: p for p in db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.organization_id == org_id))}
    subs_by_student = {}
    for sub in subscriptions:
        subs_by_student.setdefault(sub.student_id, []).append(sub)

    payments = list(db.scalars(select(Payment).where(Payment.organization_id == org_id)))
    payments_by_student = {}
    for payment in payments:
        payments_by_student.setdefault(payment.student_id, []).append(payment)

    def row_for(student):
        linked = contacts_by_student.get(student.id, [])
        parent_names = "; ".join(c.full_name for _, c in linked)
        parent_phones = "; ".join(c.phone for _, c in linked)
        parent_emails = "; ".join(c.email for _, c in linked if c.email)
        enrolls = active_enrollments.get(student.id, [])
        group_names = "; ".join(groups[e.group_id].name for e in enrolls if e.group_id in groups)
        group_times = "; ".join(
            f"{groups[e.group_id].name}: {', '.join(schedule_by_group.get(e.group_id, []))}"
            for e in enrolls if e.group_id in groups
        )
        trial_text = "; ".join(
            f"{value(t.starts_at)} — {value(t.status)}; нотатки: {t.teacher_notes or ''}"
            for t in trials_by_student.get(student.id, [])
        )
        sub_text = "; ".join(
            f"{value(s.status)} — {plans[s.plan_id].name if s.plan_id in plans else 'Тариф'}; "
            f"{s.price_minor / 100:.2f} грн; {value(s.starts_on)}–{value(s.ends_on)}"
            for s in subs_by_student.get(student.id, [])
        )
        pay_text = "; ".join(
            f"{p.amount_minor / 100:.2f} {p.currency}; {value(p.status)}; термін: {value(p.due_date)}; "
            f"оплачено: {value(p.paid_at)}; спосіб: {value(p.method)}; {p.note or ''}"
            for p in payments_by_student.get(student.id, [])
        )
        return [
            str(student.id), f"{student.first_name} {student.last_name or ''}".strip(),
            student.birth_date, student.age_at_inquiry, student.phone,
            parent_names, parent_phones, parent_emails, group_names or "Без групи", group_times,
            student.student_status, student.crm_status, student.source, student.school_shift,
            student.notes, student.next_contact_at, student.deferred_until, student.deferred_reason,
            student.deferred_note, student.lead_close_reason, student.lead_close_note,
            student.created_at, trial_text, sub_text, pay_text,
        ]

    headers = [
        "ID учня", "ПІБ учня", "Дата народження", "Вік на момент заявки", "Телефон учня",
        "ПІБ батьків / контактів", "Телефони батьків", "Email батьків", "Група", "Розклад групи",
        "Статус учня", "Статус заявки", "Джерело", "Зміна навчання", "Примітки",
        "Наступний контакт", "Повернутися після", "Причина відкладення", "Коментар відкладення",
        "Причина закриття", "Коментар закриття", "Створено", "Історія пробних занять",
        "Абонементи", "Оплати",
    ]
    active_rows, potential_rows = [], []
    for student in students:
        (potential_rows if student.student_status == StudentStatus.PROSPECT else active_rows).append(row_for(student))
    active_rows.sort(key=lambda row: (str(row[8]).casefold(), str(row[1]).casefold()))
    potential_rows.sort(key=lambda row: (str(value(row[11])).casefold(), str(row[1]).casefold()))

    book = Workbook()
    book.remove(book.active)
    make_sheet(book, "Учні", headers, active_rows)
    make_sheet(book, "Потенційні", headers, potential_rows)

    names = {s.id: f"{s.first_name} {s.last_name or ''}".strip() for s in students}
    parent_rows = []
    for student in students:
        for link, contact in contacts_by_student.get(student.id, []):
            parent_rows.append([
                names[student.id], str(student.id), contact.full_name, link.relation,
                "Так" if link.is_primary else "Ні", contact.phone, contact.email, contact.notes,
            ])
    make_sheet(book, "Батьки та контакти", [
        "Учень", "ID учня", "ПІБ контакту", "Зв’язок", "Основний контакт", "Телефон", "Email", "Примітки",
    ], parent_rows)

    comment_rows = []
    for comment in comments:
        author = users.get(comment.author_user_id)
        comment_rows.append([
            names.get(comment.student_id, ""), str(comment.student_id), comment.created_at,
            comment.updated_at, comment.kind, author.full_name if author else "", comment.body,
        ])
    make_sheet(book, "Коментарі та історія", [
        "Учень", "ID учня", "Дата", "Оновлено", "Тип події", "Автор", "Коментар / опис",
    ], comment_rows)

    group_rows = []
    for group in sorted(groups.values(), key=lambda item: item.name.casefold()):
        roster = [
            names[e.student_id] for e in enrollments
            if e.group_id == group.id and e.status == EnrollmentStatus.ACTIVE and e.student_id in names
        ]
        group_rows.append([
            group.name, "Активна" if group.is_active else "Неактивна", group.capacity,
            group.min_age, group.max_age, ", ".join(schedule_by_group.get(group.id, [])),
            "; ".join(roster),
        ])
    make_sheet(book, "Групи та розклад", [
        "Група", "Статус", "Місткість", "Вік від", "Вік до", "Розклад", "Учні",
    ], group_rows)

    payment_rows = []
    for payment in payments:
        payment_rows.append([
            names.get(payment.student_id, ""), str(payment.student_id), payment.created_at,
            payment.due_date, payment.paid_at, payment.amount_minor / 100, payment.currency,
            payment.status, payment.method, payment.note,
        ])
    make_sheet(book, "Оплати", [
        "Учень", "ID учня", "Створено", "Термін оплати", "Оплачено", "Сума", "Валюта",
        "Статус", "Спосіб", "Примітка",
    ], payment_rows)

    subscription_rows = []
    for sub in subscriptions:
        plan = plans.get(sub.plan_id)
        subscription_rows.append([
            names.get(sub.student_id, ""), str(sub.student_id), plan.name if plan else "",
            sub.status, sub.starts_on, sub.ends_on, sub.price_minor / 100, sub.period_days,
            sub.lessons_included, sub.credit_minor / 100, sub.discount_minor / 100,
            sub.discount_label, "Так" if sub.auto_renew else "Ні",
        ])
    make_sheet(book, "Абонементи", [
        "Учень", "ID учня", "Тариф", "Статус", "Початок", "Завершення", "Ціна, грн",
        "Період, днів", "Занять включено", "Кредит, грн", "Знижка, грн", "Причина знижки",
        "Автопродовження",
    ], subscription_rows)

    output = BytesIO()
    book.save(output)
    return output.getvalue()
