from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    AuditEvent,
    Contact,
    Enrollment,
    EnrollmentStatus,
    LessonSession,
    MakeupCredit,
    Payment,
    PaymentReminder,
    PaymentTransaction,
    Student,
    StudentAvailability,
    StudentContact,
    StudentStatus,
    StudentSubscription,
    SubscriptionPause,
    SubscriptionUsage,
    TrialLesson,
)
from app.models.hardening import EnrollmentHistory, IndividualAttendance, IndividualLessonSession, IndividualSubscriptionUsage
from app.services import crm


def _model_dict(row, fields: list[str]) -> dict:
    return {field: getattr(row, field) for field in fields}


def export_student_data(db: Session, org_id: UUID, student_id: UUID) -> dict:
    student = crm.scoped_get(db, Student, org_id, student_id)
    contacts = list(db.execute(
        select(Contact, StudentContact)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            Contact.organization_id == org_id,
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student.id,
        )
    ).all())
    trials = list(db.scalars(select(TrialLesson).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.student_id == student.id,
    ).order_by(TrialLesson.starts_at)))
    enrollments = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
    ).order_by(Enrollment.started_at)))
    enrollment_history = list(db.scalars(select(EnrollmentHistory).where(
        EnrollmentHistory.organization_id == org_id,
        EnrollmentHistory.student_id == student.id,
    ).order_by(EnrollmentHistory.started_at)))
    availability = list(db.scalars(select(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student.id,
    )))
    attendance = list(db.execute(
        select(Attendance, LessonSession)
        .join(LessonSession, LessonSession.id == Attendance.session_id)
        .where(Attendance.organization_id == org_id, Attendance.student_id == student.id)
        .order_by(LessonSession.starts_at)
    ).all())
    individual = list(db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.student_id == student.id,
    ).order_by(IndividualLessonSession.starts_at)))
    subscriptions = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student.id,
    ).order_by(StudentSubscription.starts_on)))
    subscription_ids = [row.id for row in subscriptions]
    usage = list(db.scalars(select(SubscriptionUsage).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.student_id == student.id,
    )))
    individual_usage = list(db.scalars(select(IndividualSubscriptionUsage).where(
        IndividualSubscriptionUsage.organization_id == org_id,
        IndividualSubscriptionUsage.student_id == student.id,
    )))
    makeup = list(db.scalars(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.student_id == student.id,
    )))
    pauses = list(db.scalars(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.student_id == student.id,
    )))
    payments = list(db.scalars(select(Payment).where(
        Payment.organization_id == org_id,
        Payment.student_id == student.id,
    ).order_by(Payment.created_at)))
    payment_ids = [row.id for row in payments]
    transactions = list(db.scalars(select(PaymentTransaction).where(
        PaymentTransaction.organization_id == org_id,
        PaymentTransaction.student_id == student.id,
    ).order_by(PaymentTransaction.occurred_at)))
    reminders = list(db.scalars(select(PaymentReminder).where(
        PaymentReminder.organization_id == org_id,
        PaymentReminder.student_id == student.id,
    ).order_by(PaymentReminder.sent_at)))
    audit = list(db.scalars(select(AuditEvent).where(
        AuditEvent.organization_id == org_id,
        AuditEvent.entity_type == "student",
        AuditEvent.entity_id == student.id,
    ).order_by(AuditEvent.created_at)))

    return {
        "exported_at": datetime.now(timezone.utc),
        "student": _model_dict(student, [
            "id", "first_name", "last_name", "phone", "birth_date", "age_at_inquiry", "source",
            "preferred_location_id", "crm_status", "student_status", "next_contact_at", "deferred_until",
            "deferred_reason", "deferred_note", "lead_close_reason", "lead_close_note", "notes", "created_at",
        ]),
        "contacts": [{
            **_model_dict(contact, ["id", "full_name", "phone", "email", "notes", "created_at"]),
            "relation": link.relation,
            "is_primary": link.is_primary,
        } for contact, link in contacts],
        "availability": [_model_dict(row, ["weekday", "start_time", "end_time", "preference", "note"]) for row in availability],
        "trials": [_model_dict(row, ["id", "location_id", "starts_at", "status", "recommended_level", "teacher_notes"]) for row in trials],
        "enrollments": [_model_dict(row, ["id", "group_id", "status", "started_at", "ended_at", "schedule_match", "schedule_note"]) for row in enrollments],
        "enrollment_history": [_model_dict(row, ["id", "group_id", "started_at", "ended_at", "status", "archived_at"]) for row in enrollment_history],
        "attendance": [{
            **_model_dict(mark, ["id", "session_id", "status", "note", "updated_at"]),
            "starts_at": session.starts_at,
            "group_id": session.group_id,
            "topic": session.topic,
        } for mark, session in attendance],
        "individual_lessons": [_model_dict(row, [
            "id", "location_id", "room_id", "staff_id", "starts_at", "duration_minutes", "topic", "notes", "status", "finalized_at",
        ]) for row in individual],
        "subscriptions": [_model_dict(row, [
            "id", "plan_id", "group_id", "status", "starts_on", "ends_on", "price_minor", "period_days",
            "lessons_included", "credit_minor", "discount_minor", "discount_label", "auto_renew", "renewal_of_id", "created_at",
        ]) for row in subscriptions],
        "subscription_usage": [_model_dict(row, ["id", "subscription_id", "session_id", "units", "source_status", "created_at"]) for row in usage],
        "individual_subscription_usage": [_model_dict(row, ["id", "subscription_id", "session_id", "units", "source_status", "created_at"]) for row in individual_usage],
        "makeup_credits": [_model_dict(row, ["id", "original_session_id", "target_session_id", "status", "expires_on", "completed_at", "created_at"]) for row in makeup],
        "subscription_pauses": [_model_dict(row, ["id", "subscription_id", "starts_on", "ends_on", "note", "resumed_at", "created_at"]) for row in pauses],
        "payments": [{
            **_model_dict(row, ["id", "subscription_id", "amount_minor", "currency", "status", "method", "due_date", "paid_at", "note", "created_at"]),
            "financials": crm.payment_financials(db, org_id, row),
        } for row in payments],
        "payment_transactions": [_model_dict(row, ["id", "payment_id", "kind", "amount_minor", "method", "note", "occurred_at"]) for row in transactions],
        "payment_reminders": [_model_dict(row, ["id", "payment_id", "stage", "channel", "sent_at", "created_by_user_id"]) for row in reminders],
        "audit_events": [_model_dict(row, ["id", "event_type", "payload", "actor_user_id", "created_at"]) for row in audit],
        "record_counts": {
            "subscriptions": len(subscription_ids),
            "payments": len(payment_ids),
        },
    }


def anonymize_archived_student(db: Session, org_id: UUID, student_id: UUID, actor_user_id: UUID | None) -> Student:
    student = db.scalar(select(Student).where(
        Student.organization_id == org_id,
        Student.id == student_id,
    ).with_for_update())
    if student is None:
        raise HTTPException(status_code=404, detail="Учня не знайдено")
    if student.student_status != StudentStatus.ARCHIVED:
        raise HTTPException(status_code=409, detail="Перед анонімізацією учня потрібно архівувати")
    open_enrollment = db.scalar(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    ).limit(1))
    if open_enrollment is not None:
        raise HTTPException(status_code=409, detail="У студента ще є активне або призупинене зарахування")
    for payment in db.scalars(select(Payment).where(Payment.organization_id == org_id, Payment.student_id == student.id)):
        if crm.payment_financials(db, org_id, payment)["balance_minor"] > 0:
            raise HTTPException(status_code=409, detail="Перед анонімізацією потрібно закрити фінансовий борг")
    for subscription in db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student.id,
    )):
        subscription.auto_renew = False
        subscription.discount_label = None
    for pause in db.scalars(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.student_id == student.id,
    )):
        pause.note = None
    for mark in db.scalars(select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.student_id == student.id,
    )):
        mark.note = None
    for lesson in db.scalars(select(IndividualLessonSession).where(
        IndividualLessonSession.organization_id == org_id,
        IndividualLessonSession.student_id == student.id,
    )):
        lesson.notes = None
    for trial in db.scalars(select(TrialLesson).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.student_id == student.id,
    )):
        trial.teacher_notes = None
    for slot in db.scalars(select(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student.id,
    )):
        slot.note = None

    links = list(db.scalars(select(StudentContact).where(
        StudentContact.organization_id == org_id,
        StudentContact.student_id == student.id,
    )))
    for link in links:
        other_link = db.scalar(select(StudentContact.id).where(
            StudentContact.organization_id == org_id,
            StudentContact.contact_id == link.contact_id,
            StudentContact.student_id != student.id,
        ).limit(1))
        if other_link is None:
            contact = crm.scoped_get(db, Contact, org_id, link.contact_id)
            contact.full_name = "Анонімізований контакт"
            contact.phone = f"redacted-{str(contact.id)[:24]}"
            contact.email = None
            contact.notes = None

    student.first_name = f"Архів-{str(student.id)[:8]}"
    student.last_name = None
    student.phone = None
    student.birth_date = None
    student.age_at_inquiry = None
    student.source = None
    student.preferred_location_id = None
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    student.lead_close_reason = None
    student.lead_close_note = None
    student.notes = None
    crm.record_audit(db, org_id, "student", student.id, "student.anonymized", {
        "reason": "privacy_request_or_retention_policy",
    }, actor_user_id)
    db.commit()
    db.refresh(student)
    return student


def retention_candidates(db: Session, org_id: UUID, older_than_days: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    rows = list(db.scalars(select(Student).where(
        Student.organization_id == org_id,
        Student.student_status == StudentStatus.ARCHIVED,
        Student.created_at < cutoff,
    ).order_by(Student.created_at)))
    return [{
        "student_id": row.id,
        "name": " ".join(filter(None, [row.first_name, row.last_name])),
        "created_at": row.created_at,
    } for row in rows]
