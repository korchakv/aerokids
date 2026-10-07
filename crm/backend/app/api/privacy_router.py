from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_db, get_org_access
from app.models.core import StaffRole
from app.services import hardening, privacy


router = APIRouter(prefix="/privacy", tags=["privacy"])


def _require_student_data(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)) -> OrgAccess:
    if not hardening.has_capability(db, access.organization_id, access.user_id, access.role, "students.manage"):
        raise HTTPException(status_code=403, detail="Недостатньо прав для експорту даних учня")
    return access


def _require_owner(access: OrgAccess = Depends(get_org_access)) -> OrgAccess:
    if access.role != StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Анонімізація доступна лише власнику організації")
    return access


@router.get("/students/{student_id}/export")
def export_student(
    student_id: UUID,
    access: OrgAccess = Depends(_require_student_data),
    db: Session = Depends(get_db),
):
    data = privacy.export_student_data(db, access.organization_id, student_id)
    # payment_financials includes ORM transaction rows for internal use; the
    # export already contains transactions separately, so return only scalars.
    for payment in data["payments"]:
        financials = payment.get("financials") or {}
        financials.pop("transactions", None)
    return jsonable_encoder(data)


@router.get("/retention-candidates")
def list_retention_candidates(
    older_than_days: int = Query(default=1095, ge=30, le=3650),
    access: OrgAccess = Depends(_require_owner),
    db: Session = Depends(get_db),
):
    return privacy.retention_candidates(db, access.organization_id, older_than_days)


@router.post("/students/{student_id}/anonymize")
def anonymize_student(
    student_id: UUID,
    access: OrgAccess = Depends(_require_owner),
    db: Session = Depends(get_db),
):
    student = privacy.anonymize_archived_student(db, access.organization_id, student_id, access.user_id)
    return {
        "student_id": student.id,
        "student_status": student.student_status,
        "anonymized": True,
    }
