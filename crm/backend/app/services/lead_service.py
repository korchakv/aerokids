from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    Contact,
    CrmStatus,
    Organization,
    PublicIntakeThrottle,
    Student,
    StudentContact,
    StudentStatus,
)
from app.schemas import IntakeCreate, LeadDetailsUpdate
from app.services import crm

# Lazy-loaded by the legacy crm facade after crm.py has initialized.
# These aliases keep routing and behavior stable while the lead/intake
# domain lives in its own module.
normalize_phone = crm.normalize_phone
scoped_get = crm.scoped_get
record_audit = crm.record_audit

def enforce_public_intake_rate_limit(
    db: Session,
    org_id: UUID,
    scope: str,
    fingerprint: str,
    limit: int,
    window_minutes: int,
) -> None:
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    row = db.scalar(
        select(PublicIntakeThrottle)
        .where(
            PublicIntakeThrottle.organization_id == org_id,
            PublicIntakeThrottle.scope == scope,
            PublicIntakeThrottle.fingerprint_hash == digest,
        )
        .with_for_update()
    )

    if row is None:
        row = PublicIntakeThrottle(
            organization_id=org_id,
            scope=scope,
            fingerprint_hash=digest,
            window_started_at=now,
            request_count=1,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return

    window_started = row.window_started_at
    if window_started.tzinfo is None:
        window_started = window_started.replace(tzinfo=timezone.utc)

    if now - window_started >= timedelta(minutes=window_minutes):
        row.window_started_at = now
        row.request_count = 1
    else:
        if row.request_count >= limit:
            raise HTTPException(status_code=429, detail="Too many form submissions. Please try again later.")
        row.request_count += 1

    row.updated_at = now
    db.commit()


def find_intake_phone_duplicates(
    db: Session,
    org_id: UUID,
    child_first_name: str,
    child_age: int,
    phone: str,
    child_phone: str | None = None,
) -> list[dict]:
    parent_phone = normalize_phone(phone)
    normalized_child_phone = normalize_phone(child_phone) if child_phone else None
    normalized_name = child_first_name.strip().casefold()
    matches: dict[UUID, dict] = {}

    direct_numbers = {value for value in (parent_phone, normalized_child_phone) if value}
    if direct_numbers:
        direct_students = list(db.scalars(select(Student).where(
            Student.organization_id == org_id,
            Student.phone.in_(direct_numbers),
        )))
        for student in direct_students:
            matched_phone = student.phone or parent_phone
            matches[student.id] = {
                "student": student,
                "matched_phone": matched_phone,
                "matched_as": "student",
                "likely_same_student": True,
            }

    contact_rows = db.execute(
        select(Student, Contact)
        .join(StudentContact, StudentContact.student_id == Student.id)
        .join(Contact, Contact.id == StudentContact.contact_id)
        .where(
            Student.organization_id == org_id,
            StudentContact.organization_id == org_id,
            Contact.organization_id == org_id,
            Contact.phone.in_(direct_numbers),
        )
    ).all() if direct_numbers else []

    for student, contact in contact_rows:
        same_child = (
            student.first_name.strip().casefold() == normalized_name
            and student.age_at_inquiry == child_age
        )
        existing = matches.get(student.id)
        if existing:
            existing["matched_as"] = "student_and_contact"
            existing["likely_same_student"] = existing["likely_same_student"] or same_child
            existing["contact"] = contact
        else:
            matches[student.id] = {
                "student": student,
                "contact": contact,
                "matched_phone": contact.phone,
                "matched_as": "contact",
                "likely_same_student": same_child,
            }

    result: list[dict] = []
    for item in matches.values():
        student = item["student"]
        contact = item.get("contact")
        if contact is None:
            contact = db.scalar(
                select(Contact)
                .join(StudentContact, StudentContact.contact_id == Contact.id)
                .where(
                    StudentContact.organization_id == org_id,
                    StudentContact.student_id == student.id,
                    Contact.organization_id == org_id,
                )
                .order_by(StudentContact.is_primary.desc(), Contact.created_at)
                .limit(1)
            )
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "crm_status": student.crm_status,
            "student_status": student.student_status,
            "student_phone": student.phone,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "matched_phone": item["matched_phone"],
            "matched_as": item["matched_as"],
            "likely_same_student": item["likely_same_student"],
        })
    return sorted(result, key=lambda item: (not item["likely_same_student"], item["first_name"].casefold()))


def _append_repeat_intake_note(organization: Organization, student: Student, data: IntakeCreate) -> None:
    try:
        local_tz = ZoneInfo(organization.timezone)
    except Exception:
        local_tz = timezone.utc
    local_now = datetime.now(timezone.utc).astimezone(local_tz)
    source_label = "через сайт" if data.source == "website" else f"· {data.source}"
    lines = [f"Повторне звернення {source_label} — {local_now.strftime('%d.%m.%Y %H:%M')}"]
    if data.comment and data.comment.strip():
        lines.append(f"Коментар: {data.comment.strip()}")
    repeat_note = "\n".join(lines)
    student.notes = f"{student.notes.rstrip()}\n\n{repeat_note}" if student.notes and student.notes.strip() else repeat_note


def create_intake(db: Session, organization: Organization, data: IntakeCreate, actor_user_id: UUID | None = None, record_repeat: bool = False) -> tuple[Student, Contact]:
    phone = normalize_phone(data.phone)
    contact = db.scalar(select(Contact).where(Contact.organization_id == organization.id, Contact.phone == phone))
    if contact is None:
        contact = Contact(organization_id=organization.id, full_name=data.contact_name, phone=phone, notes=data.comment)
        db.add(contact)
        db.flush()
    elif not contact.full_name.strip() and data.contact_name.strip():
        contact.full_name = data.contact_name.strip()

    candidate_students = list(db.scalars(
        select(Student)
        .join(StudentContact, StudentContact.student_id == Student.id)
        .where(
            Student.organization_id == organization.id,
            StudentContact.organization_id == organization.id,
            StudentContact.contact_id == contact.id,
            Student.age_at_inquiry == data.child_age,
        )
        .order_by(Student.created_at.desc())
    ))
    normalized_child_name = data.child_first_name.strip().casefold()
    existing_student = next(
        (student for student in candidate_students if student.first_name.strip().casefold() == normalized_child_name),
        None,
    )
    if existing_student is not None:
        if data.child_last_name and not existing_student.last_name:
            existing_student.last_name = data.child_last_name
        if data.child_phone and not existing_student.phone:
            existing_student.phone = data.child_phone
        if record_repeat:
            _append_repeat_intake_note(organization, existing_student, data)
        elif data.comment and not existing_student.notes:
            existing_student.notes = data.comment
        if data.source and not existing_student.source:
            existing_student.source = data.source
        record_audit(
            db,
            organization.id,
            "student",
            existing_student.id,
            "lead.duplicate_intake",
            {"source": data.source, "contact_id": str(contact.id), "repeat": record_repeat, "comment": data.comment},
            actor_user_id=actor_user_id,
        )
        db.commit()
        db.refresh(existing_student)
        db.refresh(contact)
        return existing_student, contact

    student = Student(
        organization_id=organization.id,
        first_name=data.child_first_name.strip(),
        last_name=data.child_last_name,
        phone=data.child_phone,
        age_at_inquiry=data.child_age,
        source=data.source,
        notes=data.comment,
    )
    db.add(student)
    db.flush()
    db.add(StudentContact(
        organization_id=organization.id,
        student_id=student.id,
        contact_id=contact.id,
        relation="parent_or_guardian",
        is_primary=True,
    ))
    record_audit(db, organization.id, "student", student.id, "lead.created", {"source": data.source, "contact_id": str(contact.id)}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(student)
    db.refresh(contact)
    return student, contact


def update_lead_details(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    data: LeadDetailsUpdate,
    actor_user_id: UUID | None = None,
) -> Student:
    student = scoped_get(db, Student, org_id, student_id)

    primary_link = db.scalar(
        select(StudentContact)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student.id,
        )
        .order_by(StudentContact.is_primary.desc(), StudentContact.id)
    )
    contact = scoped_get(db, Contact, org_id, primary_link.contact_id) if primary_link is not None else None

    before = {
        "child_name": " ".join(part for part in [student.first_name, student.last_name] if part),
        "child_phone": student.phone,
        "child_age": student.age_at_inquiry,
        "contact_name": contact.full_name if contact else None,
        "contact_phone": contact.phone if contact else None,
        "source": student.source,
        "comment": student.notes,
    }

    student.first_name = data.child_first_name
    student.last_name = data.child_last_name
    student.phone = data.child_phone
    student.age_at_inquiry = data.child_age
    student.source = data.source
    student.notes = data.comment

    if contact is None:
        contact = Contact(
            organization_id=org_id,
            full_name=data.contact_name,
            phone=data.phone,
        )
        db.add(contact)
        db.flush()
        primary_link = StudentContact(
            organization_id=org_id,
            student_id=student.id,
            contact_id=contact.id,
            relation="parent_or_guardian",
            is_primary=True,
        )
        db.add(primary_link)
    else:
        contact.full_name = data.contact_name
        contact.phone = data.phone

    after = {
        "child_name": " ".join(part for part in [student.first_name, student.last_name] if part),
        "child_phone": student.phone,
        "child_age": student.age_at_inquiry,
        "contact_name": contact.full_name,
        "contact_phone": contact.phone,
        "source": student.source,
        "comment": student.notes,
    }
    changed_fields = [key for key, value in after.items() if before.get(key) != value]

    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "lead.details_updated",
        {
            "changed_fields": changed_fields,
            "source": student.source,
            "comment_changed": before["comment"] != after["comment"],
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(student)
    return student


def update_student_crm_status(db: Session, org_id: UUID, student_id: UUID, status, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.crm_status = status
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    record_audit(db, org_id, "student", student.id, "student.crm_status_changed", {"crm_status": status.value if hasattr(status, "value") else str(status)}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(student)
    return student


def defer_lead(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    deferred_until: datetime | None,
    reason: str | None,
    note: str | None,
    actor_user_id: UUID | None = None,
) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    if student.student_status != StudentStatus.PROSPECT:
        raise HTTPException(status_code=409, detail="Відкласти можна лише активну заявку, не зарахованого учня.")

    if deferred_until is not None:
        now = datetime.now(timezone.utc)
        value = deferred_until if deferred_until.tzinfo else deferred_until.replace(tzinfo=timezone.utc)
        if value <= now:
            raise HTTPException(status_code=422, detail="Дата повернення має бути в майбутньому.")
        student.deferred_until = deferred_until
        student.deferred_reason = reason
        student.deferred_note = note
        student.next_contact_at = deferred_until
        event_type = "lead.deferred"
        payload = {"deferred_until": deferred_until.isoformat(), "reason": reason, "note": note}
    else:
        student.deferred_until = None
        student.deferred_reason = None
        student.deferred_note = None
        student.next_contact_at = None
        event_type = "lead.deferred_cleared"
        payload = {}

    record_audit(db, org_id, "student", student.id, event_type, payload, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(student)
    return student


def update_lead_outcome(db: Session, org_id: UUID, student_id: UUID, data, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.crm_status = data.crm_status
    student.next_contact_at = data.next_contact_at
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None

    if data.crm_status in {CrmStatus.DECLINED, CrmStatus.NO_RESPONSE, CrmStatus.NOT_RELEVANT}:
        student.lead_close_reason = data.close_reason
        student.lead_close_note = data.close_note
        student.next_contact_at = None
    else:
        student.lead_close_reason = None
        student.lead_close_note = None

    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "lead.outcome_updated",
        {
            "crm_status": data.crm_status.value,
            "next_contact_at": data.next_contact_at.isoformat() if data.next_contact_at else None,
            "close_reason": data.close_reason,
            "close_note": data.close_note,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(student)
    return student

