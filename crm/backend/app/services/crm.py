import re
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Contact, CrmStatus, Enrollment, Group, Location, Organization, Student, StudentContact, StudentStatus, TrialLesson
from app.schemas import ContactCreate, EnrollmentCreate, GroupCreate, IntakeCreate, LocationCreate, OrganizationCreate, StudentCreate, TrialLessonCreate


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("380") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+38{digits}"
    if len(digits) == 9:
        return f"+380{digits}"
    raise HTTPException(status_code=422, detail="Invalid Ukrainian phone number")


def create_organization(db: Session, data: OrganizationCreate) -> Organization:
    item = Organization(**data.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Organization slug already exists") from exc
    db.refresh(item)
    return item


def list_organizations(db: Session) -> list[Organization]:
    return list(db.scalars(select(Organization).order_by(Organization.name)))


def require_organization(db: Session, org_id: UUID) -> Organization:
    item = db.get(Organization, org_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return item


def scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_location(db: Session, org_id: UUID, data: LocationCreate) -> Location:
    require_organization(db, org_id)
    item = Location(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_locations(db: Session, org_id: UUID) -> list[Location]:
    return list(db.scalars(select(Location).where(Location.organization_id == org_id).order_by(Location.name)))


def create_contact(db: Session, org_id: UUID, data: ContactCreate) -> Contact:
    require_organization(db, org_id)
    phone = normalize_phone(data.phone)
    existing = db.scalar(select(Contact).where(Contact.organization_id == org_id, Contact.phone == phone))
    if existing:
        return existing
    item = Contact(organization_id=org_id, **data.model_dump(exclude={"phone"}), phone=phone)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_contacts(db: Session, org_id: UUID) -> list[Contact]:
    return list(db.scalars(select(Contact).where(Contact.organization_id == org_id).order_by(Contact.full_name)))


def create_student(db: Session, org_id: UUID, data: StudentCreate) -> Student:
    require_organization(db, org_id)
    item = Student(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_students(db: Session, org_id: UUID) -> list[Student]:
    return list(db.scalars(select(Student).where(Student.organization_id == org_id).order_by(Student.created_at.desc())))


def attach_contact(db: Session, org_id: UUID, student_id: UUID, contact_id: UUID, relation: str | None, is_primary: bool) -> StudentContact:
    scoped_get(db, Student, org_id, student_id)
    scoped_get(db, Contact, org_id, contact_id)
    link = db.scalar(select(StudentContact).where(StudentContact.organization_id == org_id, StudentContact.student_id == student_id, StudentContact.contact_id == contact_id))
    if link:
        return link
    link = StudentContact(organization_id=org_id, student_id=student_id, contact_id=contact_id, relation=relation, is_primary=is_primary)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def create_trial(db: Session, org_id: UUID, data: TrialLessonCreate) -> TrialLesson:
    student = scoped_get(db, Student, org_id, data.student_id)
    if data.location_id:
        scoped_get(db, Location, org_id, data.location_id)
    item = TrialLesson(organization_id=org_id, **data.model_dump())
    db.add(item)
    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    db.commit()
    db.refresh(item)
    return item


def list_trials(db: Session, org_id: UUID) -> list[TrialLesson]:
    return list(db.scalars(select(TrialLesson).where(TrialLesson.organization_id == org_id).order_by(TrialLesson.starts_at)))


def create_group(db: Session, org_id: UUID, data: GroupCreate) -> Group:
    require_organization(db, org_id)
    if data.location_id:
        scoped_get(db, Location, org_id, data.location_id)
    if data.min_age and data.max_age and data.min_age > data.max_age:
        raise HTTPException(status_code=422, detail="min_age cannot be greater than max_age")
    item = Group(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_groups(db: Session, org_id: UUID) -> list[Group]:
    return list(db.scalars(select(Group).where(Group.organization_id == org_id, Group.is_active.is_(True)).order_by(Group.name)))


def create_enrollment(db: Session, org_id: UUID, data: EnrollmentCreate) -> Enrollment:
    scoped_get(db, Student, org_id, data.student_id)
    scoped_get(db, Group, org_id, data.group_id)
    payload = data.model_dump()
    if payload["started_at"] is None:
        payload["started_at"] = date.today()
    item = Enrollment(organization_id=org_id, **payload)
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Student is already enrolled in this group") from exc
    db.refresh(item)
    return item


def create_intake(db: Session, organization: Organization, data: IntakeCreate) -> tuple[Student, Contact]:
    phone = normalize_phone(data.phone)
    contact = db.scalar(select(Contact).where(Contact.organization_id == organization.id, Contact.phone == phone))
    if contact is None:
        contact = Contact(organization_id=organization.id, full_name=data.contact_name, phone=phone, notes=data.comment)
        db.add(contact)
        db.flush()
    student = Student(organization_id=organization.id, first_name=data.child_first_name, age_at_inquiry=data.child_age, source=data.source, notes=data.comment)
    db.add(student)
    db.flush()
    db.add(StudentContact(organization_id=organization.id, student_id=student.id, contact_id=contact.id, relation="parent_or_guardian", is_primary=True))
    db.commit()
    db.refresh(student)
    db.refresh(contact)
    return student, contact


def update_student_crm_status(db: Session, org_id: UUID, student_id: UUID, status) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.crm_status = status
    db.commit()
    db.refresh(student)
    return student


def student_detail(db: Session, org_id: UUID, student_id: UUID) -> tuple[Student, list[Contact], list[TrialLesson]]:
    student = scoped_get(db, Student, org_id, student_id)
    contacts = list(db.scalars(
        select(Contact)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student_id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.full_name)
    ))
    trials = list(db.scalars(
        select(TrialLesson)
        .where(TrialLesson.organization_id == org_id, TrialLesson.student_id == student_id)
        .order_by(TrialLesson.starts_at.desc())
    ))
    return student, contacts, trials


def complete_trial(db: Session, org_id: UUID, trial_id: UUID, status, recommended_level: str | None, teacher_notes: str | None) -> TrialLesson:
    trial = scoped_get(db, TrialLesson, org_id, trial_id)
    trial.status = status
    trial.recommended_level = recommended_level
    trial.teacher_notes = teacher_notes
    student = scoped_get(db, Student, org_id, trial.student_id)
    if status.value == "completed":
        student.crm_status = CrmStatus.WAITING_FOR_GROUP
    elif status.value == "no_show":
        student.crm_status = CrmStatus.CONTACTED
    db.commit()
    db.refresh(trial)
    return trial


def list_waiting_candidates(db: Session, org_id: UUID) -> list[dict]:
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.crm_status == CrmStatus.WAITING_FOR_GROUP)
        .order_by(Student.age_at_inquiry, Student.created_at)
    ))
    result: list[dict] = []
    for student in students:
        latest_trial = db.scalar(
            select(TrialLesson)
            .where(
                TrialLesson.organization_id == org_id,
                TrialLesson.student_id == student.id,
            )
            .order_by(TrialLesson.starts_at.desc())
            .limit(1)
        )
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "recommended_level": latest_trial.recommended_level if latest_trial else None,
            "source": student.source,
        })
    return result


def form_group(db: Session, org_id: UUID, data) -> tuple[Group, list[UUID]]:
    require_organization(db, org_id)
    if data.location_id:
        scoped_get(db, Location, org_id, data.location_id)
    if data.min_age and data.max_age and data.min_age > data.max_age:
        raise HTTPException(status_code=422, detail="min_age cannot be greater than max_age")
    if len(set(data.student_ids)) != len(data.student_ids):
        raise HTTPException(status_code=422, detail="Duplicate students are not allowed")
    if len(data.student_ids) > data.capacity:
        raise HTTPException(status_code=422, detail="Selected students exceed group capacity")

    students: list[Student] = []
    for student_id in data.student_ids:
        student = scoped_get(db, Student, org_id, student_id)
        if student.crm_status != CrmStatus.WAITING_FOR_GROUP:
            raise HTTPException(status_code=409, detail=f"Student {student_id} is not waiting for a group")
        students.append(student)

    group = Group(
        organization_id=org_id,
        location_id=data.location_id,
        name=data.name,
        capacity=data.capacity,
        min_age=data.min_age,
        max_age=data.max_age,
    )
    db.add(group)
    try:
        db.flush()
        for student in students:
            db.add(Enrollment(
                organization_id=org_id,
                student_id=student.id,
                group_id=group.id,
                started_at=date.today(),
            ))
            student.crm_status = CrmStatus.ENROLLED
            student.student_status = StudentStatus.ACTIVE
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not form group; check name and enrollments") from exc

    db.refresh(group)
    return group, [student.id for student in students]


def student_profile(db: Session, org_id: UUID, student_id: UUID):
    student, contacts, trials = student_detail(db, org_id, student_id)
    rows = db.execute(
        select(Enrollment, Group)
        .join(Group, Group.id == Enrollment.group_id)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Group.organization_id == org_id,
        )
        .order_by(Enrollment.started_at.desc())
    ).all()
    groups = [{
        "group_id": group.id,
        "group_name": group.name,
        "enrollment_id": enrollment.id,
        "enrollment_status": enrollment.status,
        "started_at": enrollment.started_at,
        "location_id": group.location_id,
    } for enrollment, group in rows]
    return student, contacts, trials, groups


def update_student_lifecycle(db: Session, org_id: UUID, student_id: UUID, status: StudentStatus) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.student_status = status
    if status == StudentStatus.ARCHIVED:
        active_enrollments = list(db.scalars(select(Enrollment).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Enrollment.status == "ACTIVE",
        )))
        for enrollment in active_enrollments:
            enrollment.status = "FINISHED"
            enrollment.ended_at = date.today()
    db.commit()
    db.refresh(student)
    return student


def transfer_student(db: Session, org_id: UUID, student_id: UUID, to_group_id: UUID, started_at: date | None = None) -> Enrollment:
    student = scoped_get(db, Student, org_id, student_id)
    target = scoped_get(db, Group, org_id, to_group_id)

    active_enrollments = list(db.scalars(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student_id,
        Enrollment.status == "ACTIVE",
    )))
    for enrollment in active_enrollments:
        if enrollment.group_id == target.id:
            return enrollment
        enrollment.status = "FINISHED"
        enrollment.ended_at = (started_at or date.today())

    existing = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student_id,
        Enrollment.group_id == target.id,
    ))
    if existing:
        existing.status = "ACTIVE"
        existing.started_at = started_at or date.today()
        existing.ended_at = None
        enrollment = existing
    else:
        enrollment = Enrollment(
            organization_id=org_id,
            student_id=student.id,
            group_id=target.id,
            started_at=started_at or date.today(),
        )
        db.add(enrollment)

    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    db.commit()
    db.refresh(enrollment)
    return enrollment
