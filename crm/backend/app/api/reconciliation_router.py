from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.models.core import AttendanceStatus
from app.schemas import AttendanceBulkUpdate, AttendanceRead, LessonSessionRead
from app.services import hardening, reconciliation


router = APIRouter()


class IndividualAttendanceCreate(BaseModel):
    status: AttendanceStatus
    note: str | None = Field(default=None, max_length=300)


class IndividualAttendanceRead(BaseModel):
    id: UUID
    session_id: UUID
    student_id: UUID
    status: str
    note: str | None


def _require_attendance(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "attendance.manage"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для журналу відвідування")
    return access


@router.put("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def save_group_attendance(
    session_id: UUID,
    data: AttendanceBulkUpdate,
    access: OrgAccess = Depends(_require_attendance),
    db: Session = Depends(get_db),
):
    return reconciliation.save_group_attendance(
        db,
        access.organization_id,
        session_id,
        data.items,
        access.user_id,
        access.role,
    )


@router.post("/lesson-sessions/{session_id}/reopen", response_model=LessonSessionRead)
def reopen_group_lesson(
    session_id: UUID,
    access: OrgAccess = Depends(_require_attendance),
    db: Session = Depends(get_db),
):
    return reconciliation.reopen_group_lesson(
        db,
        access.organization_id,
        session_id,
        access.user_id,
        access.role,
    )


@router.put("/individual-lessons/{session_id}/attendance", response_model=IndividualAttendanceRead)
def save_individual_attendance(
    session_id: UUID,
    data: IndividualAttendanceCreate,
    access: OrgAccess = Depends(_require_attendance),
    db: Session = Depends(get_db),
):
    return reconciliation.save_individual_attendance(
        db,
        access.organization_id,
        session_id,
        data.status,
        data.note,
        access.user_id,
    )
