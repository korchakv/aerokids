from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_org_id
from app.models.core import Organization
from app.schemas import ContactCreate, ContactRead, EnrollmentCreate, EnrollmentRead, GroupCreate, GroupRead, IntakeCreate, IntakeResult, LocationCreate, LocationRead, OrganizationCreate, OrganizationRead, StudentContactCreate, StudentCreate, StudentRead, TrialLessonCreate, TrialLessonRead
from app.services import crm

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/organizations", response_model=OrganizationRead, status_code=201)
def create_organization(data: OrganizationCreate, db: Session = Depends(get_db)):
    return crm.create_organization(db, data)


@router.get("/organizations", response_model=list[OrganizationRead])
def organizations(db: Session = Depends(get_db)):
    return crm.list_organizations(db)


@router.post("/locations", response_model=LocationRead, status_code=201)
def create_location(data: LocationCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_location(db, org_id, data)


@router.get("/locations", response_model=list[LocationRead])
def locations(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_locations(db, org_id)


@router.post("/contacts", response_model=ContactRead, status_code=201)
def create_contact(data: ContactCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_contact(db, org_id, data)


@router.get("/contacts", response_model=list[ContactRead])
def contacts(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_contacts(db, org_id)


@router.post("/students", response_model=StudentRead, status_code=201)
def create_student(data: StudentCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_student(db, org_id, data)


@router.get("/students", response_model=list[StudentRead])
def students(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_students(db, org_id)


@router.post("/students/{student_id}/contacts", status_code=201)
def add_student_contact(student_id: UUID, data: StudentContactCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    item = crm.attach_contact(db, org_id, student_id, data.contact_id, data.relation, data.is_primary)
    return {"id": str(item.id)}


@router.post("/trial-lessons", response_model=TrialLessonRead, status_code=201)
def create_trial(data: TrialLessonCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_trial(db, org_id, data)


@router.get("/trial-lessons", response_model=list[TrialLessonRead])
def trials(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_trials(db, org_id)


@router.post("/groups", response_model=GroupRead, status_code=201)
def create_group(data: GroupCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_group(db, org_id, data)


@router.get("/groups", response_model=list[GroupRead])
def groups(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_groups(db, org_id)


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment(data: EnrollmentCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_enrollment(db, org_id, data)


@router.post("/public/intake/{organization_slug}", response_model=IntakeResult, status_code=201)
def public_intake(organization_slug: str, data: IntakeCreate, db: Session = Depends(get_db)):
    organization = db.scalar(select(Organization).where(Organization.slug == organization_slug))
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    student, contact = crm.create_intake(db, organization, data)
    return IntakeResult(student_id=student.id, contact_id=contact.id, crm_status=student.crm_status)
