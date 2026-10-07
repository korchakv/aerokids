from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.schemas import EnrollmentCreate, EnrollmentRead, StudentTransfer
from app.services import enrollment_hardening, hardening


router = APIRouter()


def _require_students(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "students.manage"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для роботи з учнями")
    return access


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment(
    data: EnrollmentCreate,
    access: OrgAccess = Depends(_require_students),
    db: Session = Depends(get_db),
):
    return enrollment_hardening.enroll(
        db,
        access.organization_id,
        data.student_id,
        data.group_id,
        data.started_at,
        access.user_id,
    )


@router.post("/students/{student_id}/transfer", response_model=EnrollmentRead)
def transfer_student(
    student_id: UUID,
    data: StudentTransfer,
    access: OrgAccess = Depends(_require_students),
    db: Session = Depends(get_db),
):
    return enrollment_hardening.transfer(
        db,
        access.organization_id,
        student_id,
        data.to_group_id,
        data.started_at,
        access.user_id,
    )
