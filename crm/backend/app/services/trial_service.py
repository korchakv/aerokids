from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.core import CrmStatus, Location, Student, TrialLesson, TrialStatus
from app.services import audit_service


def _scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_trial(
    db: Session,
    org_id: UUID,
    data,
    actor_user_id: UUID | None = None,
) -> TrialLesson:
    student = _scoped_get(db, Student, org_id, data.student_id)
    if data.location_id:
        _scoped_get(db, Location, org_id, data.location_id)

    item = TrialLesson(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.flush()

    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    student.lead_close_reason = None
    student.lead_close_note = None

    audit_service.record_audit(
        db,
        org_id,
        "student",
        student.id,
        "trial.scheduled",
        {"trial_id": str(item.id), "starts_at": item.starts_at.isoformat()},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(item)
    return item


def update_trial(
    db: Session,
    org_id: UUID,
    trial_id: UUID,
    starts_at: datetime | None,
    location_id: UUID | None,
    actor_user_id: UUID | None = None,
) -> TrialLesson:
    trial = _scoped_get(db, TrialLesson, org_id, trial_id)
    if location_id is not None:
        _scoped_get(db, Location, org_id, location_id)
        trial.location_id = location_id
    if starts_at is not None:
        trial.starts_at = starts_at

    trial.status = TrialStatus.SCHEDULED
    student = _scoped_get(db, Student, org_id, trial.student_id)
    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    student.lead_close_reason = None
    student.lead_close_note = None

    audit_service.record_audit(
        db,
        org_id,
        "student",
        student.id,
        "trial.rescheduled",
        {
            "trial_id": str(trial.id),
            "starts_at": trial.starts_at.isoformat(),
            "location_id": str(trial.location_id) if trial.location_id else None,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(trial)
    return trial


def list_trials(db: Session, org_id: UUID) -> list[TrialLesson]:
    return list(
        db.scalars(
            select(TrialLesson)
            .where(TrialLesson.organization_id == org_id)
            .order_by(TrialLesson.starts_at)
        )
    )


def complete_trial(db: Session, org_id: UUID, trial_id: UUID, status, recommended_level: str | None, teacher_notes: str | None, actor_user_id: UUID | None = None) -> TrialLesson:
    trial = _scoped_get(db, TrialLesson, org_id, trial_id)
    was_completed = trial.status == TrialStatus.COMPLETED
    preserve_current_stage = was_completed and status == TrialStatus.COMPLETED
    trial.status = status
    trial.recommended_level = recommended_level
    trial.teacher_notes = teacher_notes
    student = _scoped_get(db, Student, org_id, trial.student_id)
    if not preserve_current_stage:
        student.lead_close_reason = None
        student.lead_close_note = None
    if preserve_current_stage:
        # Editing a saved completed result must not change the student's current CRM stage.
        pass
    elif status.value == "completed":
        # A completed trial still needs an explicit business decision:
        # ready for a group, thinking/follow-up, or declined.
        student.crm_status = CrmStatus.TRIAL_COMPLETED
        student.next_contact_at = None
    elif status.value == "no_show":
        # No-show remains an active lead that needs contact/rescheduling.
        student.crm_status = CrmStatus.CONTACTED
        student.next_contact_at = None
    elif status.value == "cancelled":
        student.crm_status = CrmStatus.CONTACTED
        student.next_contact_at = None
    audit_service.record_audit(
        db,
        org_id,
        "student",
        student.id,
        f"trial.{status.value}",
        {"trial_id": str(trial.id), "recommended_level": recommended_level, "teacher_notes": teacher_notes},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(trial)
    return trial


