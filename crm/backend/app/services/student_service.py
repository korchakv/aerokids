from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    Contact,
    Enrollment,
    MakeupCredit,
    Organization,
    Payment,
    PaymentReminder,
    PaymentTransaction,
    Student,
    StudentAvailability,
    StudentContact,
    StudentSubscription,
    SubscriptionPause,
    SubscriptionUsage,
    TrialLesson,
    TrialStatus,
)
from app.services import audit_service


def _require_organization(db: Session, org_id: UUID) -> Organization:
    organization = db.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def _scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_student(db: Session, org_id: UUID, data) -> Student:
    _require_organization(db, org_id)
    item = Student(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_students(db: Session, org_id: UUID) -> list[Student]:
    return list(
        db.scalars(
            select(Student)
            .where(Student.organization_id == org_id)
            .order_by(Student.created_at.desc())
        )
    )


def delete_student(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    student = _scoped_get(db, Student, org_id, student_id)

    enrollment = db.scalar(
        select(Enrollment.id)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student.id,
        )
        .limit(1)
    )
    if enrollment is not None:
        raise HTTPException(
            status_code=409,
            detail="Учень уже був зарахований до групи. Щоб не втратити історію навчання, видалити його не можна — використайте «Архів».",
        )

    completed_trial = db.scalar(
        select(TrialLesson.id)
        .where(
            TrialLesson.organization_id == org_id,
            TrialLesson.student_id == student.id,
            TrialLesson.status == TrialStatus.COMPLETED,
        )
        .limit(1)
    )
    if completed_trial is not None:
        raise HTTPException(
            status_code=409,
            detail="У цього учня вже є завершене пробне заняття. Щоб не втратити історію, видалити його не можна — використайте «Архів».",
        )

    protected_history_checks = (
        (Attendance, "Є відмітки відвідування."),
        (StudentSubscription, "Є абонемент."),
        (SubscriptionUsage, "Є списання занять з абонемента."),
        (MakeupCredit, "Є відпрацювання."),
        (Payment, "Є фінансова історія."),
        (PaymentTransaction, "Є фінансові операції."),
        (SubscriptionPause, "Є історія пауз абонемента."),
        (PaymentReminder, "Є історія нагадувань про оплату."),
    )
    for model, reason in protected_history_checks:
        history = db.scalar(
            select(model.id)
            .where(
                model.organization_id == org_id,
                model.student_id == student.id,
            )
            .limit(1)
        )
        if history is not None:
            raise HTTPException(
                status_code=409,
                detail=f"{reason} Щоб не втратити історію учня, видалення заблоковано — використайте «Архів».",
            )

    db.execute(
        delete(StudentAvailability).where(
            StudentAvailability.organization_id == org_id,
            StudentAvailability.student_id == student.id,
        )
    )
    db.execute(
        delete(StudentContact).where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student.id,
        )
    )
    db.execute(
        delete(TrialLesson).where(
            TrialLesson.organization_id == org_id,
            TrialLesson.student_id == student.id,
        )
    )
    db.flush()

    audit_service.record_audit(
        db,
        org_id,
        "student",
        student.id,
        "student.deleted",
        {
            "name": " ".join(part for part in (student.first_name, student.last_name) if part),
            "reason": "manual_delete_before_history",
        },
        actor_user_id=actor_user_id,
    )
    db.delete(student)
    db.commit()


def attach_contact(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    contact_id: UUID,
    relation: str | None,
    is_primary: bool,
) -> StudentContact:
    _scoped_get(db, Student, org_id, student_id)
    _scoped_get(db, Contact, org_id, contact_id)
    link = db.scalar(
        select(StudentContact).where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student_id,
            StudentContact.contact_id == contact_id,
        )
    )
    if link is not None:
        return link
    link = StudentContact(
        organization_id=org_id,
        student_id=student_id,
        contact_id=contact_id,
        relation=relation,
        is_primary=is_primary,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link
