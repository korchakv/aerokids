import hashlib
import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Attendance, AttendanceStatus, AuditEvent, Contact, CrmStatus, Enrollment, EnrollmentStatus, Group, GroupSchedule, GroupStaff, LessonSession, LessonStatus, Location, Organization, OrganizationMembership, Payment, PaymentMethod, PaymentReminder, PaymentStatus, PaymentTransaction, PublicIntakeThrottle, Staff, StaffLocation, StaffRole, Student, StudentAvailability, StudentContact, StudentStatus, StudentSubscription, SubscriptionPause, SubscriptionPlan, SubscriptionStatus, TrialLesson, TrialStatus, User
from app.schemas import ContactCreate, EnrollmentCreate, GroupCreate, IntakeCreate, LocationCreate, OrganizationCreate, StudentCreate, TrialLessonCreate
from app.services.schedule_matching import enrollment_schedule_note, evaluate_schedule_match

def record_audit(
    db: Session,
    org_id: UUID,
    entity_type: str,
    entity_id: UUID | None,
    event_type: str,
    payload: dict | None = None,
    actor_user_id: UUID | None = None,
) -> AuditEvent:
    item = AuditEvent(
        organization_id=org_id,
        actor_user_id=actor_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        payload=payload,
    )
    db.add(item)
    return item


def list_audit_events(
    db: Session,
    org_id: UUID,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = 100,
) -> list[dict]:
    stmt = select(AuditEvent).where(AuditEvent.organization_id == org_id)
    if entity_type:
        stmt = stmt.where(AuditEvent.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditEvent.entity_id == entity_id)

    events = list(db.scalars(stmt.order_by(AuditEvent.created_at.desc()).limit(limit)))
    users: dict[UUID, User] = {}
    user_ids = {event.actor_user_id for event in events if event.actor_user_id is not None}
    if user_ids:
        users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids)))}

    return [{
        "id": event.id,
        "organization_id": event.organization_id,
        "actor_user_id": event.actor_user_id,
        "actor_name": users.get(event.actor_user_id).full_name if event.actor_user_id in users else None,
        "actor_email": users.get(event.actor_user_id).email if event.actor_user_id in users else None,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "event_type": event.event_type,
        "payload": event.payload,
        "created_at": event.created_at,
    } for event in events]



def ensure_group_capacity(db: Session, org_id: UUID, group: Group, student_id: UUID | None = None) -> None:
    if group.capacity is None:
        return
    already_enrolled = False
    if student_id is not None:
        already_enrolled = db.scalar(select(Enrollment.id).where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Enrollment.group_id == group.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )) is not None
    if already_enrolled:
        return

    occupied = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    )) or 0
    if occupied >= group.capacity:
        raise HTTPException(status_code=409, detail="Group has no available seats")


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


def normalize_phone(value: str) -> str:
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)

    # International numbers are accepted when the country code is explicit.
    if raw.startswith("+"):
        if 8 <= len(digits) <= 15:
            return f"+{digits}"
        raise HTTPException(status_code=422, detail="Invalid international phone number")

    # Ukrainian shorthand remains convenient for the first AeroKiDS tenant.
    if digits.startswith("380") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+38{digits}"
    if len(digits) == 9:
        return f"+380{digits}"

    raise HTTPException(status_code=422, detail="Use an international phone number starting with +")


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


def update_organization(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> Organization:
    item = require_organization(db, org_id)
    updates = data.model_dump(exclude_none=True)

    next_currency = updates.get("currency")
    if next_currency and next_currency != item.currency:
        has_payments = db.scalar(
            select(Payment.id).where(Payment.organization_id == org_id).limit(1)
        ) is not None
        if has_payments:
            raise HTTPException(
                status_code=409,
                detail="Organization currency cannot be changed after payments have been created",
            )

    for key, value in updates.items():
        setattr(item, key, value)
    record_audit(db, org_id, "organization", item.id, "organization.settings_updated", updates, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(item)
    return item


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


def create_trial(db: Session, org_id: UUID, data: TrialLessonCreate, actor_user_id: UUID | None = None) -> TrialLesson:
    student = scoped_get(db, Student, org_id, data.student_id)
    if data.location_id:
        scoped_get(db, Location, org_id, data.location_id)
    item = TrialLesson(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.flush()
    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    student.next_contact_at = None
    student.lead_close_reason = None
    student.lead_close_note = None
    record_audit(db, org_id, "student", student.id, "trial.scheduled", {"trial_id": str(item.id), "starts_at": item.starts_at.isoformat()}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(item)
    return item


def update_trial(db: Session, org_id: UUID, trial_id: UUID, starts_at: datetime | None, location_id: UUID | None, actor_user_id: UUID | None = None) -> TrialLesson:
    trial = scoped_get(db, TrialLesson, org_id, trial_id)
    if location_id is not None:
        scoped_get(db, Location, org_id, location_id)
        trial.location_id = location_id
    if starts_at is not None:
        trial.starts_at = starts_at
    trial.status = TrialStatus.SCHEDULED
    student = scoped_get(db, Student, org_id, trial.student_id)
    student.crm_status = CrmStatus.TRIAL_SCHEDULED
    student.next_contact_at = None
    student.lead_close_reason = None
    student.lead_close_note = None
    record_audit(db, org_id, "student", student.id, "trial.rescheduled", {
        "trial_id": str(trial.id),
        "starts_at": trial.starts_at.isoformat(),
        "location_id": str(trial.location_id) if trial.location_id else None,
    }, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(trial)
    return trial


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
    group = scoped_get(db, Group, org_id, data.group_id)
    ensure_group_capacity(db, org_id, group, data.student_id)
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


def create_intake(db: Session, organization: Organization, data: IntakeCreate, actor_user_id: UUID | None = None) -> tuple[Student, Contact]:
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
        if data.comment and not existing_student.notes:
            existing_student.notes = data.comment
        if data.source and not existing_student.source:
            existing_student.source = data.source
        record_audit(
            db,
            organization.id,
            "student",
            existing_student.id,
            "lead.duplicate_intake",
            {"source": data.source, "contact_id": str(contact.id)},
            actor_user_id=actor_user_id,
        )
        db.commit()
        db.refresh(existing_student)
        db.refresh(contact)
        return existing_student, contact

    student = Student(
        organization_id=organization.id,
        first_name=data.child_first_name.strip(),
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


def update_student_crm_status(db: Session, org_id: UUID, student_id: UUID, status, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.crm_status = status
    record_audit(db, org_id, "student", student.id, "student.crm_status_changed", {"crm_status": status.value if hasattr(status, "value") else str(status)}, actor_user_id=actor_user_id)
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


def complete_trial(db: Session, org_id: UUID, trial_id: UUID, status, recommended_level: str | None, teacher_notes: str | None, actor_user_id: UUID | None = None) -> TrialLesson:
    trial = scoped_get(db, TrialLesson, org_id, trial_id)
    trial.status = status
    trial.recommended_level = recommended_level
    trial.teacher_notes = teacher_notes
    student = scoped_get(db, Student, org_id, trial.student_id)
    student.lead_close_reason = None
    student.lead_close_note = None
    if status.value == "completed":
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
    record_audit(
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


def update_lead_outcome(db: Session, org_id: UUID, student_id: UUID, data, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.crm_status = data.crm_status
    student.next_contact_at = data.next_contact_at

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


def form_group(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> tuple[Group, list[UUID]]:
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
        schedule_keys: set[tuple[int, str]] = set()
        for slot in data.schedule_slots:
            key = (slot.weekday, slot.start_time)
            if key in schedule_keys:
                raise HTTPException(status_code=422, detail="Duplicate group schedule slots are not allowed")
            schedule_keys.add(key)
            db.add(GroupSchedule(
                organization_id=org_id,
                group_id=group.id,
                weekday=slot.weekday,
                start_time=time.fromisoformat(slot.start_time),
                duration_minutes=slot.duration_minutes,
            ))

        for student in students:
            windows = list(db.scalars(select(StudentAvailability).where(
                StudentAvailability.organization_id == org_id,
                StudentAvailability.student_id == student.id,
            )))
            match = evaluate_schedule_match(data.schedule_slots, windows, data.location_id, student.preferred_location_id)
            note = enrollment_schedule_note(match, data.schedule_slots, windows)
            db.add(Enrollment(
                organization_id=org_id,
                student_id=student.id,
                group_id=group.id,
                started_at=date.today(),
                schedule_match=match.status,
                schedule_note=note,
            ))
            student.crm_status = CrmStatus.ENROLLED
            student.student_status = StudentStatus.ACTIVE
            record_audit(db, org_id, "student", student.id, "student.enrolled", {
                "group_id": str(group.id), "group_name": group.name,
                "schedule_match": match.status, "schedule_note": note,
            }, actor_user_id=actor_user_id)
        record_audit(db, org_id, "group", group.id, "group.created", {
            "name": group.name,
            "student_count": len(students),
            "schedule_slots": len(data.schedule_slots),
        }, actor_user_id=actor_user_id)
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


def update_student_lifecycle(db: Session, org_id: UUID, student_id: UUID, status: StudentStatus, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.student_status = status
    record_audit(db, org_id, "student", student.id, "student.status_changed", {"student_status": status.value}, actor_user_id=actor_user_id)
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


def transfer_student(db: Session, org_id: UUID, student_id: UUID, to_group_id: UUID, started_at: date | None = None, actor_user_id: UUID | None = None) -> Enrollment:
    student = scoped_get(db, Student, org_id, student_id)
    target = scoped_get(db, Group, org_id, to_group_id)
    ensure_group_capacity(db, org_id, target, student_id)

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
    record_audit(db, org_id, "student", student.id, "student.transferred", {"to_group_id": str(target.id), "to_group_name": target.name}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def create_group_schedule(db: Session, org_id: UUID, data) -> GroupSchedule:
    scoped_get(db, Group, org_id, data.group_id)
    item = GroupSchedule(
        organization_id=org_id,
        group_id=data.group_id,
        weekday=data.weekday,
        start_time=time.fromisoformat(data.start_time),
        duration_minutes=data.duration_minutes,
    )
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="This group already has the same schedule slot") from exc
    db.refresh(item)
    return item


def list_group_schedules(db: Session, org_id: UUID, group_id: UUID | None = None, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[GroupSchedule]:
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(GroupSchedule).where(GroupSchedule.organization_id == org_id, GroupSchedule.is_active.is_(True))
    if group_id is not None:
        ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(GroupSchedule.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(GroupSchedule.group_id.in_(allowed))
    return list(db.scalars(stmt.order_by(GroupSchedule.weekday, GroupSchedule.start_time)))


def group_roster(db: Session, org_id: UUID, group_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    ensure_group_access(db, org_id, user_id, role, group_id)
    rows = db.execute(
        select(Student)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group_id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
            Student.organization_id == org_id,
            Student.student_status == StudentStatus.ACTIVE,
        )
        .order_by(Student.first_name, Student.last_name)
    ).scalars().all()
    return [{
        "student_id": student.id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "age": student.age_at_inquiry,
    } for student in rows]


def group_detail(db: Session, org_id: UUID, group_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> dict:
    if role == StaffRole.ACCOUNTANT:
        group = scoped_get(db, Group, org_id, group_id)
    else:
        group = ensure_group_access(db, org_id, user_id, role, group_id)

    schedules = list(db.scalars(
        select(GroupSchedule)
        .where(
            GroupSchedule.organization_id == org_id,
            GroupSchedule.group_id == group.id,
            GroupSchedule.is_active.is_(True),
        )
        .order_by(GroupSchedule.weekday, GroupSchedule.start_time)
    ))
    enrollments = list(db.scalars(
        select(Enrollment)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group.id,
            Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
        )
        .order_by(Enrollment.started_at, Enrollment.id)
    ))
    finance_visible = role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.ACCOUNTANT}
    members = []
    today = date.today()

    for enrollment in enrollments:
        student = scoped_get(db, Student, org_id, enrollment.student_id)
        contact = _primary_contact_for_student(db, org_id, student.id)

        attendance_rows = list(db.scalars(
            select(Attendance)
            .join(LessonSession, LessonSession.id == Attendance.session_id)
            .where(
                Attendance.organization_id == org_id,
                Attendance.student_id == student.id,
                LessonSession.organization_id == org_id,
                LessonSession.group_id == group.id,
            )
        ))
        attendance_counts = {
            "present": sum(row.status == AttendanceStatus.PRESENT for row in attendance_rows),
            "absent": sum(row.status == AttendanceStatus.ABSENT for row in attendance_rows),
            "late": sum(row.status == AttendanceStatus.LATE for row in attendance_rows),
            "excused": sum(row.status == AttendanceStatus.EXCUSED for row in attendance_rows),
        }
        attendance_total = len(attendance_rows)
        attended = attendance_counts["present"] + attendance_counts["late"]
        attendance_summary = {
            **attendance_counts,
            "total": attendance_total,
            "attendance_rate": round(attended / attendance_total * 100, 1) if attendance_total else 0.0,
        }

        billing = None
        payment_rows: list[Payment] = []
        if finance_visible:
            payment_rows = list(db.scalars(
                select(Payment)
                .where(Payment.organization_id == org_id, Payment.student_id == student.id)
                .order_by(Payment.created_at.desc())
            ))
            subscriptions = list(db.scalars(
                select(StudentSubscription)
                .where(StudentSubscription.organization_id == org_id, StudentSubscription.student_id == student.id)
                .order_by(StudentSubscription.starts_on.desc())
            ))
            subscription_by_id = {item.id: item for item in subscriptions}
            for payment in payment_rows:
                linked = subscription_by_id.get(payment.subscription_id) if payment.subscription_id else None
                payment.plan_id = linked.plan_id if linked else None
                _attach_payment_financials(db, org_id, payment)

            latest_subscription = subscriptions[0] if subscriptions else None
            plan = scoped_get(db, SubscriptionPlan, org_id, latest_subscription.plan_id) if latest_subscription else None
            pending = [item for item in payment_rows if item.status != PaymentStatus.CANCELLED and item.balance_minor > 0]
            dated_pending = [item for item in pending if item.due_date is not None]
            overdue = [item for item in dated_pending if item.due_date < today]
            due_today = [item for item in dated_pending if item.due_date == today]
            next_due_date = min((item.due_date for item in dated_pending), default=None)
            last_paid = next((item for item in payment_rows if item.paid_minor - item.refunded_minor > 0), None)
            if overdue:
                billing_status = "overdue"
            elif due_today:
                billing_status = "due"
            elif pending:
                billing_status = "upcoming"
            elif latest_subscription and latest_subscription.status == SubscriptionStatus.ACTIVE and latest_subscription.ends_on >= today:
                billing_status = "current"
            else:
                billing_status = "no_plan"

            billing = {
                "status": billing_status,
                "plan_name": plan.name if plan else None,
                "amount_due_minor": sum(item.balance_minor for item in pending),
                "next_due_date": next_due_date,
                "last_paid_at": last_paid.paid_at if last_paid else None,
                "last_paid_minor": (last_paid.paid_minor - last_paid.refunded_minor) if last_paid else None,
                "subscription_ends_on": latest_subscription.ends_on if latest_subscription else None,
            }

        members.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "enrollment_started_at": enrollment.started_at,
            "enrollment_status": enrollment.status,
            "attendance": attendance_summary,
            "billing": billing,
            "payments": payment_rows,
        })

    return {"group": group, "schedules": schedules, "members": members}


def create_lesson_session(db: Session, org_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    group = ensure_group_access(db, org_id, user_id, role, data.group_id)
    location_id = data.location_id if data.location_id is not None else group.location_id
    if location_id is not None:
        scoped_get(db, Location, org_id, location_id)
    item = LessonSession(
        organization_id=org_id,
        group_id=group.id,
        location_id=location_id,
        starts_at=data.starts_at,
        duration_minutes=data.duration_minutes,
        topic=data.topic,
        notes=data.notes,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_lesson_sessions(db: Session, org_id: UUID, group_id: UUID | None = None, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[LessonSession]:
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(LessonSession).where(LessonSession.organization_id == org_id)
    if group_id is not None:
        ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(LessonSession.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(LessonSession.group_id.in_(allowed))
    return list(db.scalars(stmt.order_by(LessonSession.starts_at)))


def mark_attendance_bulk(db: Session, org_id: UUID, session_id: UUID, items, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[Attendance]:
    session = scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    roster_ids = {item["student_id"] for item in group_roster(db, org_id, session.group_id, user_id, role)}
    submitted_ids = [item.student_id for item in items]
    if len(set(submitted_ids)) != len(submitted_ids):
        raise HTTPException(status_code=422, detail="Duplicate students in attendance payload")
    if not set(submitted_ids).issubset(roster_ids):
        raise HTTPException(status_code=409, detail="Attendance can only be marked for active students in this group")

    result: list[Attendance] = []
    for mark in items:
        row = db.scalar(select(Attendance).where(
            Attendance.organization_id == org_id,
            Attendance.session_id == session.id,
            Attendance.student_id == mark.student_id,
        ))
        if row is None:
            row = Attendance(
                organization_id=org_id,
                session_id=session.id,
                student_id=mark.student_id,
                status=mark.status,
                note=mark.note,
            )
            db.add(row)
        else:
            row.status = mark.status
            row.note = mark.note
        result.append(row)

    if roster_ids and roster_ids.issubset(set(submitted_ids)):
        session.status = LessonStatus.COMPLETED

    record_audit(db, org_id, "lesson_session", session.id, "attendance.saved", {"marked_count": len(result), "group_id": str(session.group_id)}, actor_user_id=user_id)
    db.commit()
    for row in result:
        db.refresh(row)
    return result


def list_attendance(db: Session, org_id: UUID, session_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[Attendance]:
    session = scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    return list(db.scalars(
        select(Attendance)
        .where(Attendance.organization_id == org_id, Attendance.session_id == session_id)
        .order_by(Attendance.student_id)
    ))


def _payment_transactions(db: Session, org_id: UUID, payment_id: UUID) -> list[PaymentTransaction]:
    return list(db.scalars(
        select(PaymentTransaction)
        .where(
            PaymentTransaction.organization_id == org_id,
            PaymentTransaction.payment_id == payment_id,
        )
        .order_by(PaymentTransaction.occurred_at, PaymentTransaction.id)
    ))


def _materialize_legacy_settlement(db: Session, org_id: UUID, payment: Payment) -> None:
    transactions = _payment_transactions(db, org_id, payment.id)
    if transactions or payment.status != PaymentStatus.PAID:
        return
    db.add(PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind="payment",
        amount_minor=payment.amount_minor,
        method=payment.method.value if payment.method else None,
        note="Legacy full payment migrated to ledger",
        occurred_at=payment.paid_at or payment.created_at,
    ))
    db.flush()


def payment_financials(db: Session, org_id: UUID, payment: Payment) -> dict:
    transactions = _payment_transactions(db, org_id, payment.id)
    increases = sum(item.amount_minor for item in transactions if item.kind == "adjustment_increase")
    decreases = sum(item.amount_minor for item in transactions if item.kind == "adjustment_decrease")
    adjusted_amount = max(0, payment.amount_minor + increases - decreases)
    paid_minor = sum(item.amount_minor for item in transactions if item.kind == "payment")
    refunded_minor = sum(item.amount_minor for item in transactions if item.kind == "refund")

    # Backward compatibility for charges that were fully paid before ledger transactions existed.
    if not transactions and payment.status == PaymentStatus.PAID:
        paid_minor = adjusted_amount

    net_paid = max(0, paid_minor - refunded_minor)
    balance = max(0, adjusted_amount - net_paid)
    return {
        "adjusted_amount_minor": adjusted_amount,
        "paid_minor": paid_minor,
        "refunded_minor": refunded_minor,
        "net_paid_minor": net_paid,
        "balance_minor": balance,
        "transactions": transactions,
    }


def _sync_payment_state(db: Session, org_id: UUID, payment: Payment) -> dict:
    finance = payment_financials(db, org_id, payment)
    if payment.status != PaymentStatus.CANCELLED:
        if finance["adjusted_amount_minor"] == 0 and finance["net_paid_minor"] == 0 and finance["refunded_minor"] > 0:
            payment.status = PaymentStatus.REFUNDED
        elif finance["balance_minor"] == 0 and finance["adjusted_amount_minor"] > 0:
            payment.status = PaymentStatus.PAID
        else:
            payment.status = PaymentStatus.PENDING
    payment.adjusted_amount_minor = finance["adjusted_amount_minor"]
    payment.paid_minor = finance["paid_minor"]
    payment.refunded_minor = finance["refunded_minor"]
    payment.balance_minor = finance["balance_minor"]
    return finance


def _attach_payment_financials(db: Session, org_id: UUID, payment: Payment) -> Payment:
    finance = payment_financials(db, org_id, payment)
    payment.adjusted_amount_minor = finance["adjusted_amount_minor"]
    payment.paid_minor = finance["paid_minor"]
    payment.refunded_minor = finance["refunded_minor"]
    payment.balance_minor = finance["balance_minor"]
    return payment


def create_subscription_plan(db: Session, org_id: UUID, data) -> SubscriptionPlan:
    require_organization(db, org_id)
    item = SubscriptionPlan(organization_id=org_id, **data.model_dump())
    db.add(item)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Subscription plan name already exists") from exc
    db.refresh(item)
    return item


def list_subscription_plans(db: Session, org_id: UUID) -> list[SubscriptionPlan]:
    return list(db.scalars(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.organization_id == org_id, SubscriptionPlan.is_active.is_(True))
        .order_by(SubscriptionPlan.name)
    ))


def create_student_subscription(db: Session, org_id: UUID, data) -> StudentSubscription:
    student = scoped_get(db, Student, org_id, data.student_id)
    plan = scoped_get(db, SubscriptionPlan, org_id, data.plan_id)
    price_minor = data.price_minor if data.price_minor is not None else plan.price_minor
    if data.discount_minor > price_minor:
        raise HTTPException(status_code=422, detail="Discount cannot exceed subscription price")
    ends_on = data.starts_on + timedelta(days=plan.period_days - 1)
    item = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        starts_on=data.starts_on,
        ends_on=ends_on,
        price_minor=price_minor,
        discount_minor=data.discount_minor,
        discount_label=data.discount_label,
        auto_renew=getattr(data, "auto_renew", False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_student_subscriptions(db: Session, org_id: UUID, student_id: UUID | None = None) -> list[StudentSubscription]:
    stmt = select(StudentSubscription).where(StudentSubscription.organization_id == org_id)
    if student_id is not None:
        scoped_get(db, Student, org_id, student_id)
        stmt = stmt.where(StudentSubscription.student_id == student_id)
    return list(db.scalars(stmt.order_by(StudentSubscription.starts_on.desc())))


def set_subscription_auto_renew(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    auto_renew: bool,
    actor_user_id: UUID | None = None,
) -> StudentSubscription:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled subscription cannot be renewed")
    subscription.auto_renew = auto_renew
    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.auto_renew_changed",
        {"subscription_id": str(subscription.id), "auto_renew": auto_renew},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(subscription)
    return subscription


def pause_subscription(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    starts_on: date,
    resume_on: date | None = None,
    note: str | None = None,
    actor_user_id: UUID | None = None,
) -> SubscriptionPause:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status in {SubscriptionStatus.CANCELLED, SubscriptionStatus.EXPIRED}:
        raise HTTPException(status_code=409, detail="Subscription cannot be paused")
    if starts_on < subscription.starts_on or starts_on > subscription.ends_on:
        raise HTTPException(status_code=422, detail="Pause must start inside the subscription period")

    existing = db.scalar(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.subscription_id == subscription.id,
        SubscriptionPause.resumed_at.is_(None),
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="Subscription already has an active or scheduled pause")

    ends_on = resume_on - timedelta(days=1) if resume_on else None
    pause = SubscriptionPause(
        organization_id=org_id,
        subscription_id=subscription.id,
        student_id=subscription.student_id,
        starts_on=starts_on,
        ends_on=ends_on,
        note=note,
    )
    db.add(pause)
    today = date.today()
    if starts_on <= today and (ends_on is None or today <= ends_on):
        subscription.status = SubscriptionStatus.PAUSED
    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.paused",
        {
            "subscription_id": str(subscription.id),
            "starts_on": starts_on.isoformat(),
            "resume_on": resume_on.isoformat() if resume_on else None,
            "note": note,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(pause)
    return pause


def _finish_subscription_pause(
    db: Session,
    org_id: UUID,
    subscription: StudentSubscription,
    pause: SubscriptionPause,
    resumes_on: date,
    actor_user_id: UUID | None = None,
    automatic: bool = False,
) -> None:
    if resumes_on <= pause.starts_on:
        raise HTTPException(status_code=422, detail="Resume date must be after pause start")
    pause_end = resumes_on - timedelta(days=1)
    if pause.ends_on is not None and pause_end > pause.ends_on:
        pause_end = pause.ends_on
        resumes_on = pause_end + timedelta(days=1)
    pause.ends_on = pause_end
    pause.resumed_at = datetime.now(timezone.utc)
    paused_days = (pause_end - pause.starts_on).days + 1
    subscription.ends_on = subscription.ends_on + timedelta(days=paused_days)
    subscription.status = SubscriptionStatus.ACTIVE if subscription.ends_on >= resumes_on else SubscriptionStatus.EXPIRED
    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.resumed",
        {
            "subscription_id": str(subscription.id),
            "resumes_on": resumes_on.isoformat(),
            "paused_days": paused_days,
            "automatic": automatic,
        },
        actor_user_id=actor_user_id,
    )


def resume_subscription(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    resumes_on: date | None = None,
    actor_user_id: UUID | None = None,
) -> StudentSubscription:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    pause = db.scalar(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.subscription_id == subscription.id,
        SubscriptionPause.resumed_at.is_(None),
    ).order_by(SubscriptionPause.created_at.desc()))
    if pause is None:
        raise HTTPException(status_code=409, detail="Subscription has no active pause")

    resume_date = resumes_on or date.today()
    _finish_subscription_pause(db, org_id, subscription, pause, resume_date, actor_user_id)
    db.commit()
    db.refresh(subscription)
    return subscription


def _resume_due_pauses(db: Session, org_id: UUID, today: date, actor_user_id: UUID | None = None) -> int:
    rows = list(db.scalars(select(SubscriptionPause).where(
        SubscriptionPause.organization_id == org_id,
        SubscriptionPause.resumed_at.is_(None),
        SubscriptionPause.ends_on.is_not(None),
        SubscriptionPause.ends_on < today,
    )))
    count = 0
    for pause in rows:
        subscription = scoped_get(db, StudentSubscription, org_id, pause.subscription_id)
        _finish_subscription_pause(
            db,
            org_id,
            subscription,
            pause,
            pause.ends_on + timedelta(days=1),
            actor_user_id,
            automatic=True,
        )
        count += 1
    if count:
        db.commit()
    return count


def run_billing_renewals(
    db: Session,
    org_id: UUID,
    through_date: date | None = None,
    actor_user_id: UUID | None = None,
) -> dict:
    organization = require_organization(db, org_id)
    today = date.today()
    horizon = through_date or (today + timedelta(days=7))
    if horizon < today:
        raise HTTPException(status_code=422, detail="through_date cannot be in the past")

    resumed = _resume_due_pauses(db, org_id, today, actor_user_id)
    created_payment_ids: list[UUID] = []
    created_subscriptions = 0
    skipped_stale_subscriptions = 0

    candidates = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.auto_renew.is_(True),
        StudentSubscription.status == SubscriptionStatus.ACTIVE,
        StudentSubscription.ends_on <= horizon,
    ).order_by(StudentSubscription.ends_on, StudentSubscription.created_at)))

    for original in candidates:
        current = original
        while current.auto_renew and current.status == SubscriptionStatus.ACTIVE and current.ends_on <= horizon:
            open_pause = db.scalar(select(SubscriptionPause.id).where(
                SubscriptionPause.organization_id == org_id,
                SubscriptionPause.subscription_id == current.id,
                SubscriptionPause.resumed_at.is_(None),
            ))
            if open_pause is not None:
                break

            existing_child = db.scalar(select(StudentSubscription).where(
                StudentSubscription.organization_id == org_id,
                StudentSubscription.renewal_of_id == current.id,
                StudentSubscription.status != SubscriptionStatus.CANCELLED,
            ))
            if existing_child is not None:
                current = existing_child
                continue

            student = scoped_get(db, Student, org_id, current.student_id)
            if student.student_status != StudentStatus.ACTIVE:
                break
            active_enrollment = db.scalar(select(Enrollment.id).where(
                Enrollment.organization_id == org_id,
                Enrollment.student_id == student.id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
            ))
            if active_enrollment is None:
                break

            plan = scoped_get(db, SubscriptionPlan, org_id, current.plan_id)
            if current.ends_on < today - timedelta(days=plan.period_days):
                skipped_stale_subscriptions += 1
                break
            next_start = current.ends_on + timedelta(days=1)
            next_subscription = StudentSubscription(
                organization_id=org_id,
                student_id=student.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                starts_on=next_start,
                ends_on=next_start + timedelta(days=plan.period_days - 1),
                price_minor=plan.price_minor,
                discount_minor=0,
                discount_label=None,
                auto_renew=True,
                renewal_of_id=current.id,
            )
            db.add(next_subscription)
            db.flush()
            payment = Payment(
                organization_id=org_id,
                student_id=student.id,
                subscription_id=next_subscription.id,
                amount_minor=plan.price_minor,
                currency=organization.currency,
                due_date=next_start,
                note=f"{plan.name} · автоматичне продовження",
            )
            db.add(payment)
            db.flush()
            current.status = SubscriptionStatus.EXPIRED
            record_audit(
                db,
                org_id,
                "student",
                student.id,
                "subscription.renewed",
                {
                    "previous_subscription_id": str(current.id),
                    "subscription_id": str(next_subscription.id),
                    "payment_id": str(payment.id),
                    "starts_on": next_start.isoformat(),
                    "amount_minor": plan.price_minor,
                },
                actor_user_id=actor_user_id,
            )
            created_payment_ids.append(payment.id)
            created_subscriptions += 1
            current = next_subscription

    if created_subscriptions:
        db.commit()
    return {
        "resumed_subscriptions": resumed,
        "created_subscriptions": created_subscriptions,
        "skipped_stale_subscriptions": skipped_stale_subscriptions,
        "created_payment_ids": created_payment_ids,
    }


def create_subscription_charge(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> tuple[StudentSubscription, Payment]:
    organization = require_organization(db, org_id)
    student = scoped_get(db, Student, org_id, data.student_id)
    plan = scoped_get(db, SubscriptionPlan, org_id, data.plan_id)
    if data.discount_minor > plan.price_minor:
        raise HTTPException(status_code=422, detail="Discount cannot exceed subscription price")

    amount_minor = plan.price_minor - data.discount_minor
    if amount_minor <= 0:
        raise HTTPException(status_code=422, detail="Charge amount must be greater than zero")

    duplicate_subscription = db.scalar(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student.id,
        StudentSubscription.plan_id == plan.id,
        StudentSubscription.starts_on == data.starts_on,
        StudentSubscription.status != SubscriptionStatus.CANCELLED,
    ))
    if duplicate_subscription is not None:
        raise HTTPException(status_code=409, detail="This subscription period has already been charged")

    subscription = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        starts_on=data.starts_on,
        ends_on=data.starts_on + timedelta(days=plan.period_days - 1),
        price_minor=plan.price_minor,
        discount_minor=data.discount_minor,
        discount_label=data.discount_label,
        auto_renew=getattr(data, "auto_renew", False),
    )
    db.add(subscription)
    db.flush()

    payment = Payment(
        organization_id=org_id,
        student_id=student.id,
        subscription_id=subscription.id,
        amount_minor=amount_minor,
        currency=organization.currency,
        due_date=data.due_date or data.starts_on,
        note=data.note or plan.name,
    )
    db.add(payment)
    db.flush()
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "payment.created",
        {
            "payment_id": str(payment.id),
            "subscription_id": str(subscription.id),
            "plan_id": str(plan.id),
            "amount_minor": amount_minor,
            "due_date": payment.due_date.isoformat() if payment.due_date else None,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(subscription)
    db.refresh(payment)
    payment.plan_id = plan.id
    _attach_payment_financials(db, org_id, payment)
    return subscription, payment


def create_payment(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> Payment:
    organization = require_organization(db, org_id)
    student = scoped_get(db, Student, org_id, data.student_id)
    if data.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, data.subscription_id)
        if subscription.student_id != student.id:
            raise HTTPException(status_code=409, detail="Subscription belongs to another student")
    item = Payment(
        organization_id=org_id,
        student_id=student.id,
        subscription_id=data.subscription_id,
        amount_minor=data.amount_minor,
        currency=organization.currency,
        due_date=data.due_date,
        note=data.note,
    )
    db.add(item)
    db.flush()
    record_audit(db, org_id, "student", student.id, "payment.created", {"payment_id": str(item.id), "amount_minor": item.amount_minor, "due_date": item.due_date.isoformat() if item.due_date else None}, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(item)
    item.plan_id = subscription.plan_id if data.subscription_id is not None else None
    return _attach_payment_financials(db, org_id, item)


def list_payments(db: Session, org_id: UUID, student_id: UUID | None = None, status: PaymentStatus | None = None) -> list[Payment]:
    stmt = select(Payment).where(Payment.organization_id == org_id)
    if student_id is not None:
        scoped_get(db, Student, org_id, student_id)
        stmt = stmt.where(Payment.student_id == student_id)
    if status is not None:
        stmt = stmt.where(Payment.status == status)
    rows = list(db.scalars(stmt.order_by(Payment.created_at.desc())))
    for row in rows:
        if row.subscription_id is not None:
            subscription = scoped_get(db, StudentSubscription, org_id, row.subscription_id)
            row.plan_id = subscription.plan_id
        else:
            row.plan_id = None
        _attach_payment_financials(db, org_id, row)
    return rows


def add_payment_receipt(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    amount_minor: int,
    method: PaymentMethod,
    paid_at: datetime | None = None,
    note: str | None = None,
    actor_user_id: UUID | None = None,
) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status in {PaymentStatus.CANCELLED, PaymentStatus.REFUNDED}:
        raise HTTPException(status_code=409, detail="This charge cannot accept payments")

    finance = payment_financials(db, org_id, payment)
    if amount_minor > finance["balance_minor"]:
        raise HTTPException(status_code=422, detail="Payment amount exceeds outstanding balance")

    occurred_at = paid_at or datetime.now(timezone.utc)
    transaction = PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind="payment",
        amount_minor=amount_minor,
        method=method.value,
        note=note,
        occurred_at=occurred_at,
        actor_user_id=actor_user_id,
    )
    db.add(transaction)
    db.flush()
    finance = _sync_payment_state(db, org_id, payment)
    payment.method = method
    payment.paid_at = occurred_at if finance["balance_minor"] == 0 else None
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.received",
        {
            "payment_id": str(payment.id),
            "transaction_id": str(transaction.id),
            "amount_minor": amount_minor,
            "balance_minor": finance["balance_minor"],
            "method": method.value,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    if payment.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, payment.subscription_id)
        payment.plan_id = subscription.plan_id
    else:
        payment.plan_id = None
    return _attach_payment_financials(db, org_id, payment)


def mark_payment_paid(db: Session, org_id: UUID, payment_id: UUID, method: PaymentMethod, paid_at: datetime | None = None, actor_user_id: UUID | None = None) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    finance = payment_financials(db, org_id, payment)
    if payment.status in {PaymentStatus.CANCELLED, PaymentStatus.REFUNDED}:
        raise HTTPException(status_code=409, detail="This charge cannot be marked as paid")
    if finance["balance_minor"] <= 0:
        raise HTTPException(status_code=409, detail="Payment is already fully settled")
    return add_payment_receipt(
        db,
        org_id,
        payment_id,
        finance["balance_minor"],
        method,
        paid_at,
        "Full settlement",
        actor_user_id,
    )


def add_payment_adjustment(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    direction: str,
    amount_minor: int,
    reason: str,
    actor_user_id: UUID | None = None,
) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status == PaymentStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled charge cannot be adjusted")
    _materialize_legacy_settlement(db, org_id, payment)
    finance = payment_financials(db, org_id, payment)
    if direction == "decrease" and amount_minor > finance["adjusted_amount_minor"]:
        raise HTTPException(status_code=422, detail="Adjustment exceeds charge amount")
    if direction == "decrease" and finance["adjusted_amount_minor"] - amount_minor < finance["net_paid_minor"]:
        raise HTTPException(status_code=422, detail="Refund the overpaid amount before decreasing the charge")

    kind = "adjustment_increase" if direction == "increase" else "adjustment_decrease"
    db.add(PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind=kind,
        amount_minor=amount_minor,
        note=reason,
        actor_user_id=actor_user_id,
    ))
    db.flush()
    finance = _sync_payment_state(db, org_id, payment)
    if payment.status != PaymentStatus.PAID:
        payment.paid_at = None
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.adjusted",
        {
            "payment_id": str(payment.id),
            "direction": direction,
            "amount_minor": amount_minor,
            "balance_minor": finance["balance_minor"],
            "reason": reason,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    if payment.subscription_id:
        payment.plan_id = scoped_get(db, StudentSubscription, org_id, payment.subscription_id).plan_id
    else:
        payment.plan_id = None
    return _attach_payment_financials(db, org_id, payment)


def refund_payment(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    amount_minor: int,
    note: str,
    occurred_at: datetime | None = None,
    reduce_charge: bool = True,
    actor_user_id: UUID | None = None,
) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status == PaymentStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled charge cannot be refunded")
    _materialize_legacy_settlement(db, org_id, payment)
    finance = payment_financials(db, org_id, payment)
    if amount_minor > finance["net_paid_minor"]:
        raise HTTPException(status_code=422, detail="Refund exceeds net amount received")

    db.add(PaymentTransaction(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        kind="refund",
        amount_minor=amount_minor,
        note=note,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        actor_user_id=actor_user_id,
    ))
    if reduce_charge:
        db.add(PaymentTransaction(
            organization_id=org_id,
            payment_id=payment.id,
            student_id=payment.student_id,
            kind="adjustment_decrease",
            amount_minor=amount_minor,
            note=f"Refund adjustment: {note}",
            actor_user_id=actor_user_id,
        ))
    db.flush()
    finance = _sync_payment_state(db, org_id, payment)
    if finance["balance_minor"] > 0:
        payment.paid_at = None
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.refunded",
        {
            "payment_id": str(payment.id),
            "amount_minor": amount_minor,
            "reduce_charge": reduce_charge,
            "balance_minor": finance["balance_minor"],
            "reason": note,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    if payment.subscription_id:
        payment.plan_id = scoped_get(db, StudentSubscription, org_id, payment.subscription_id).plan_id
    else:
        payment.plan_id = None
    return _attach_payment_financials(db, org_id, payment)


def list_payment_transactions(db: Session, org_id: UUID, payment_id: UUID) -> list[PaymentTransaction]:
    scoped_get(db, Payment, org_id, payment_id)
    return _payment_transactions(db, org_id, payment_id)


def payment_summary(db: Session, org_id: UUID) -> dict:
    rows = list(db.scalars(select(Payment).where(Payment.organization_id == org_id)))
    today = date.today()
    paid_minor = 0
    pending_minor = 0
    overdue_minor = 0
    paid_count = 0
    pending_count = 0
    overdue_count = 0
    for row in rows:
        if row.status == PaymentStatus.CANCELLED:
            continue
        finance = payment_financials(db, org_id, row)
        paid_minor += finance["net_paid_minor"]
        if finance["balance_minor"] > 0:
            pending_minor += finance["balance_minor"]
            pending_count += 1
            if row.due_date is not None and row.due_date < today:
                overdue_minor += finance["balance_minor"]
                overdue_count += 1
        elif finance["adjusted_amount_minor"] > 0:
            paid_count += 1
    return {
        "paid_minor": paid_minor,
        "pending_minor": pending_minor,
        "overdue_minor": overdue_minor,
        "paid_count": paid_count,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
    }


def cancel_payment(db: Session, org_id: UUID, payment_id: UUID, reason: str, actor_user_id: UUID | None = None) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    finance = payment_financials(db, org_id, payment)
    if payment.status != PaymentStatus.PENDING or finance["net_paid_minor"] > 0:
        raise HTTPException(status_code=409, detail="Only unpaid pending charges can be cancelled")

    payment.status = PaymentStatus.CANCELLED
    if payment.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, payment.subscription_id)
        subscription.status = SubscriptionStatus.CANCELLED
        payment.plan_id = subscription.plan_id
    else:
        payment.plan_id = None

    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.cancelled",
        {"payment_id": str(payment.id), "reason": reason, "subscription_id": str(payment.subscription_id) if payment.subscription_id else None},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(payment)
    return _attach_payment_financials(db, org_id, payment)


def _payment_reminder_stage(due_date: date, today: date) -> tuple[str, str] | None:
    delta = (today - due_date).days
    if -3 <= delta <= -1:
        return "upcoming_3", "Оплата наближається"
    if delta == 0:
        return "due_today", "Оплата сьогодні"
    if 1 <= delta <= 2:
        return "overdue_1", "Прострочено"
    if 3 <= delta <= 6:
        return "overdue_3", "Прострочено 3+ дні"
    if 7 <= delta <= 13:
        return "overdue_7", "Прострочено 7+ днів"
    if 14 <= delta <= 29:
        return "overdue_14", "Прострочено 14+ днів"
    if delta >= 30:
        return "overdue_30", "Прострочено 30+ днів"
    return None


def payment_reminder_queue(db: Session, org_id: UUID) -> list[dict]:
    today = date.today()
    payments = list(db.scalars(
        select(Payment)
        .where(
            Payment.organization_id == org_id,
            Payment.status == PaymentStatus.PENDING,
            Payment.due_date.is_not(None),
        )
        .order_by(Payment.due_date, Payment.created_at)
    ))
    result = []
    for payment in payments:
        finance = payment_financials(db, org_id, payment)
        if finance["balance_minor"] <= 0:
            continue
        stage_info = _payment_reminder_stage(payment.due_date, today)
        if stage_info is None:
            continue
        stage, label = stage_info
        already_sent = db.scalar(select(PaymentReminder.id).where(
            PaymentReminder.organization_id == org_id,
            PaymentReminder.payment_id == payment.id,
            PaymentReminder.stage == stage,
        ))
        if already_sent is not None:
            continue
        student = scoped_get(db, Student, org_id, payment.student_id)
        contact = _primary_contact_for_student(db, org_id, student.id)
        last_reminder_at = db.scalar(select(func.max(PaymentReminder.sent_at)).where(
            PaymentReminder.organization_id == org_id,
            PaymentReminder.payment_id == payment.id,
        ))
        result.append({
            "payment_id": payment.id,
            "student_id": student.id,
            "student_name": " ".join(filter(None, [student.first_name, student.last_name])),
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "amount_minor": finance["balance_minor"],
            "currency": payment.currency,
            "due_date": payment.due_date,
            "days_from_due": (today - payment.due_date).days,
            "stage": stage,
            "label": label,
            "last_reminder_at": last_reminder_at,
        })
    return result


def mark_payment_reminder_sent(
    db: Session,
    org_id: UUID,
    payment_id: UUID,
    stage: str,
    channel: str,
    actor_user_id: UUID | None = None,
) -> PaymentReminder:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status != PaymentStatus.PENDING or payment.due_date is None:
        raise HTTPException(status_code=409, detail="Payment no longer needs a reminder")

    expected = _payment_reminder_stage(payment.due_date, date.today())
    if expected is None or expected[0] != stage:
        raise HTTPException(status_code=409, detail="Reminder stage is no longer current")

    existing = db.scalar(select(PaymentReminder).where(
        PaymentReminder.organization_id == org_id,
        PaymentReminder.payment_id == payment.id,
        PaymentReminder.stage == stage,
    ))
    if existing is not None:
        raise HTTPException(status_code=409, detail="This reminder stage was already recorded")

    item = PaymentReminder(
        organization_id=org_id,
        payment_id=payment.id,
        student_id=payment.student_id,
        stage=stage,
        channel=channel,
        created_by_user_id=actor_user_id,
    )
    db.add(item)
    record_audit(
        db,
        org_id,
        "student",
        payment.student_id,
        "payment.reminder_sent",
        {"payment_id": str(payment.id), "stage": stage, "channel": channel},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(item)
    return item


def create_staff(db: Session, org_id: UUID, data) -> Staff:
    require_organization(db, org_id)
    if data.email:
        existing = db.scalar(select(Staff).where(Staff.organization_id == org_id, Staff.email == data.email))
        if existing:
            raise HTTPException(status_code=409, detail="Staff email already exists in this organization")
    locations = []
    for location_id in data.location_ids:
        locations.append(scoped_get(db, Location, org_id, location_id))
    item = Staff(
        organization_id=org_id,
        full_name=data.full_name,
        email=data.email,
        phone=data.phone,
        role=data.role,
        notes=data.notes,
    )
    db.add(item)
    db.flush()
    for location in locations:
        db.add(StaffLocation(
            organization_id=org_id,
            staff_id=item.id,
            location_id=location.id,
        ))
    db.commit()
    db.refresh(item)
    return item


def list_staff(db: Session, org_id: UUID, active_only: bool = True) -> list[Staff]:
    stmt = select(Staff).where(Staff.organization_id == org_id)
    if active_only:
        stmt = stmt.where(Staff.is_active.is_(True))
    return list(db.scalars(stmt.order_by(Staff.full_name)))


def update_staff(db: Session, org_id: UUID, staff_id: UUID, data) -> Staff:
    item = scoped_get(db, Staff, org_id, staff_id)
    payload = data.model_dump(exclude_unset=True)
    if "email" in payload and payload["email"]:
        duplicate = db.scalar(select(Staff).where(
            Staff.organization_id == org_id,
            Staff.email == payload["email"],
            Staff.id != staff_id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Staff email already exists in this organization")
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def set_staff_locations(db: Session, org_id: UUID, staff_id: UUID, location_ids: list[UUID]) -> Staff:
    item = scoped_get(db, Staff, org_id, staff_id)
    unique_ids = list(dict.fromkeys(location_ids))
    for location_id in unique_ids:
        scoped_get(db, Location, org_id, location_id)

    existing = list(db.scalars(select(StaffLocation).where(
        StaffLocation.organization_id == org_id,
        StaffLocation.staff_id == staff_id,
    )))
    for row in existing:
        db.delete(row)
    for location_id in unique_ids:
        db.add(StaffLocation(
            organization_id=org_id,
            staff_id=staff_id,
            location_id=location_id,
        ))
    db.commit()
    db.refresh(item)
    return item


def assign_staff_to_group(db: Session, org_id: UUID, staff_id: UUID, group_id: UUID, is_primary: bool = False) -> GroupStaff:
    staff = scoped_get(db, Staff, org_id, staff_id)
    if not staff.is_active:
        raise HTTPException(status_code=409, detail="Inactive staff member cannot be assigned")
    scoped_get(db, Group, org_id, group_id)

    existing = db.scalar(select(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
        GroupStaff.group_id == group_id,
    ))
    if existing:
        existing.is_primary = is_primary
        db.commit()
        db.refresh(existing)
        return existing

    if is_primary:
        primary_rows = list(db.scalars(select(GroupStaff).where(
            GroupStaff.organization_id == org_id,
            GroupStaff.group_id == group_id,
            GroupStaff.is_primary.is_(True),
        )))
        for row in primary_rows:
            row.is_primary = False

    item = GroupStaff(
        organization_id=org_id,
        staff_id=staff_id,
        group_id=group_id,
        is_primary=is_primary,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def staff_profile(db: Session, org_id: UUID, staff_id: UUID):
    item = scoped_get(db, Staff, org_id, staff_id)
    location_ids = list(db.scalars(select(StaffLocation.location_id).where(
        StaffLocation.organization_id == org_id,
        StaffLocation.staff_id == staff_id,
    )))
    group_ids = list(db.scalars(select(GroupStaff.group_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
    )))
    return item, location_ids, group_ids


def create_membership(db: Session, org_id: UUID, data):
    require_organization(db, org_id)
    normalized_email = data.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        user = User(email=normalized_email, full_name=data.full_name)
        db.add(user)
        db.flush()

    existing = db.scalar(select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.user_id == user.id,
    ))
    if existing:
        existing.role = data.role
        existing.is_active = True
        db.commit()
        db.refresh(existing)
        return existing, user

    membership = OrganizationMembership(
        organization_id=org_id,
        user_id=user.id,
        role=data.role,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership, user


def update_location(db: Session, org_id: UUID, location_id: UUID, data) -> Location:
    item = scoped_get(db, Location, org_id, location_id)
    payload = data.model_dump(exclude_unset=True)
    if "name" in payload and payload["name"]:
        duplicate = db.scalar(select(Location).where(
            Location.organization_id == org_id,
            Location.name == payload["name"],
            Location.id != location_id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Location name already exists")
    for key, value in payload.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def overview_report(db: Session, org_id: UUID) -> dict:
    require_organization(db, org_id)

    funnel_rows = db.execute(
        select(Student.crm_status, func.count(Student.id))
        .where(Student.organization_id == org_id)
        .group_by(Student.crm_status)
    ).all()
    funnel_map = {status: count for status, count in funnel_rows}
    funnel = [
        {"status": status, "count": int(funnel_map.get(status, 0))}
        for status in CrmStatus
    ]

    active_students = db.scalar(select(func.count(Student.id)).where(
        Student.organization_id == org_id,
        Student.student_status == StudentStatus.ACTIVE,
    )) or 0

    active_groups = db.scalar(select(func.count(Group.id)).where(
        Group.organization_id == org_id,
        Group.is_active.is_(True),
    )) or 0

    enrolled_students = db.scalar(select(func.count(Enrollment.id)).where(
        Enrollment.organization_id == org_id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    )) or 0

    capacities = list(db.scalars(select(Group.capacity).where(
        Group.organization_id == org_id,
        Group.is_active.is_(True),
    )))
    group_capacity = sum(capacity or 0 for capacity in capacities)

    active_staff = db.scalar(select(func.count(Staff.id)).where(
        Staff.organization_id == org_id,
        Staff.is_active.is_(True),
    )) or 0

    active_locations = db.scalar(select(func.count(Location.id)).where(
        Location.organization_id == org_id,
        Location.is_active.is_(True),
    )) or 0

    attendance_rows = db.execute(
        select(Attendance.status, func.count(Attendance.id))
        .where(Attendance.organization_id == org_id)
        .group_by(Attendance.status)
    ).all()
    attendance_map = {status: int(count) for status, count in attendance_rows}
    present = attendance_map.get(AttendanceStatus.PRESENT, 0)
    absent = attendance_map.get(AttendanceStatus.ABSENT, 0)
    late = attendance_map.get(AttendanceStatus.LATE, 0)
    excused = attendance_map.get(AttendanceStatus.EXCUSED, 0)
    total = present + absent + late + excused
    rate = round(((present + late) / total * 100), 1) if total else 0.0

    return {
        "funnel": funnel,
        "active_students": int(active_students),
        "active_groups": int(active_groups),
        "enrolled_students": int(enrolled_students),
        "group_capacity": int(group_capacity),
        "active_staff": int(active_staff),
        "active_locations": int(active_locations),
        "attendance": {
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "total": total,
            "attendance_rate": rate,
        },
        "payments": payment_summary(db, org_id),
    }


def _primary_contact_for_student(db: Session, org_id: UUID, student_id: UUID) -> Contact | None:
    return db.scalar(
        select(Contact)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student_id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.created_at)
        .limit(1)
    )


def student_preferences(db: Session, org_id: UUID, student_id: UUID) -> dict:
    student = scoped_get(db, Student, org_id, student_id)
    location = scoped_get(db, Location, org_id, student.preferred_location_id) if student.preferred_location_id else None
    availability = list(db.scalars(
        select(StudentAvailability)
        .where(
            StudentAvailability.organization_id == org_id,
            StudentAvailability.student_id == student_id,
        )
        .order_by(StudentAvailability.weekday, StudentAvailability.start_time)
    ))
    return {
        "preferred_location_id": student.preferred_location_id,
        "preferred_location_name": location.name if location else None,
        "availability": [{
            "weekday": item.weekday,
            "start_time": item.start_time,
            "end_time": item.end_time,
            "preference": item.preference,
            "note": item.note,
        } for item in availability],
    }


def replace_student_preferences(db: Session, org_id: UUID, student_id: UUID, data, actor_user_id: UUID | None = None) -> dict:
    student = scoped_get(db, Student, org_id, student_id)
    if data.preferred_location_id is not None:
        scoped_get(db, Location, org_id, data.preferred_location_id)

    seen: set[tuple[int, time, time]] = set()
    for slot in data.availability:
        key = (slot.weekday, slot.start_time, slot.end_time)
        if key in seen:
            raise HTTPException(status_code=422, detail="Duplicate availability slots are not allowed")
        seen.add(key)

    student.preferred_location_id = data.preferred_location_id
    db.execute(delete(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student_id,
    ))
    for slot in data.availability:
        db.add(StudentAvailability(
            organization_id=org_id,
            student_id=student_id,
            weekday=slot.weekday,
            start_time=slot.start_time,
            end_time=slot.end_time,
            preference=slot.preference,
            note=slot.note,
        ))

    record_audit(db, org_id, "student", student.id, "student.preferences_updated", {
        "preferred_location_id": str(data.preferred_location_id) if data.preferred_location_id else None,
        "availability_count": len(data.availability),
    }, actor_user_id=actor_user_id)
    db.commit()
    return student_preferences(db, org_id, student_id)


def preview_group_matches(db: Session, org_id: UUID, data) -> list[dict]:
    if data.location_id is not None:
        scoped_get(db, Location, org_id, data.location_id)
    results = []
    for student_id in data.student_ids:
        student = scoped_get(db, Student, org_id, student_id)
        windows = list(db.scalars(select(StudentAvailability).where(
            StudentAvailability.organization_id == org_id,
            StudentAvailability.student_id == student.id,
        )))
        match = evaluate_schedule_match(data.schedule_slots, windows, data.location_id, student.preferred_location_id)
        results.append({
            "student_id": student.id,
            "status": match.status,
            "summary": match.summary,
            "matching_slots": [vars(item) for item in match.matching_slots],
            "partial_slots": [vars(item) for item in match.partial_slots],
            "conflicting_slots": [vars(item) for item in match.conflicting_slots],
        })
    return results


def list_lead_overview(db: Session, org_id: UUID) -> list[dict]:
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.student_status == StudentStatus.PROSPECT)
        .order_by(Student.created_at.desc())
    ))
    result = []
    for student in students:
        contact = _primary_contact_for_student(db, org_id, student.id)
        trial = db.scalar(
            select(TrialLesson)
            .where(TrialLesson.organization_id == org_id, TrialLesson.student_id == student.id)
            .order_by(TrialLesson.starts_at.desc())
            .limit(1)
        )
        trial_location = scoped_get(db, Location, org_id, trial.location_id) if trial and trial.location_id else None
        preferences = student_preferences(db, org_id, student.id)
        result.append({
            "student_id": student.id,
            "created_at": student.created_at,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "source": student.source,
            "comment": student.notes,
            "preferred_location_id": preferences["preferred_location_id"],
            "preferred_location_name": preferences["preferred_location_name"],
            "availability": preferences["availability"],
            "crm_status": student.crm_status,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "latest_trial_id": trial.id if trial else None,
            "latest_trial_at": trial.starts_at if trial else None,
            "latest_trial_status": trial.status if trial else None,
            "trial_location_id": trial.location_id if trial else None,
            "trial_location_name": trial_location.name if trial_location else None,
            "recommended_level": trial.recommended_level if trial else None,
            "teacher_notes": trial.teacher_notes if trial else None,
            "next_contact_at": student.next_contact_at,
            "close_reason": student.lead_close_reason,
            "close_note": student.lead_close_note,
        })
    return result


def list_student_overview(db: Session, org_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    allowed_groups = None if role == StaffRole.ACCOUNTANT else assigned_group_ids_for_user(db, org_id, user_id, role)
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.student_status != StudentStatus.PROSPECT)
        .order_by(Student.first_name, Student.last_name)
    ))
    result = []
    for student in students:
        contact = _primary_contact_for_student(db, org_id, student.id)
        row = db.execute(
            select(Enrollment, Group)
            .join(Group, Group.id == Enrollment.group_id)
            .where(
                Enrollment.organization_id == org_id,
                Enrollment.student_id == student.id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
                Group.organization_id == org_id,
            )
            .limit(1)
        ).first()
        enrollment, group = row if row else (None, None)
        if allowed_groups is not None and (group is None or group.id not in allowed_groups):
            continue
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "source": student.source,
            "student_status": student.student_status,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "group_id": group.id if group else None,
            "group_name": group.name if group else None,
        })
    return result


def list_group_overview(db: Session, org_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    allowed_groups = assigned_group_ids_for_user(db, org_id, user_id, role)
    groups = list(db.scalars(
        select(Group)
        .where(Group.organization_id == org_id, Group.is_active.is_(True))
        .order_by(Group.name)
    ))
    if allowed_groups is not None:
        groups = [group for group in groups if group.id in allowed_groups]
    result = []
    for group in groups:
        enrolled_count = db.scalar(select(func.count(Enrollment.id)).where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == group.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )) or 0
        location = scoped_get(db, Location, org_id, group.location_id) if group.location_id else None
        result.append({
            "group_id": group.id,
            "name": group.name,
            "location_id": group.location_id,
            "location_name": location.name if location else None,
            "capacity": group.capacity,
            "enrolled_count": int(enrolled_count),
            "min_age": group.min_age,
            "max_age": group.max_age,
        })
    return result


def assigned_group_ids_for_user(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole) -> set[UUID] | None:
    if role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER}:
        return None
    if role != StaffRole.TEACHER or user_id is None:
        return set()

    staff = db.scalar(select(Staff).where(
        Staff.organization_id == org_id,
        Staff.user_id == user_id,
        Staff.is_active.is_(True),
    ))
    if staff is None:
        return set()
    return set(db.scalars(select(GroupStaff.group_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff.id,
    )))


def ensure_group_access(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, group_id: UUID) -> Group:
    group = scoped_get(db, Group, org_id, group_id)
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed is not None and group_id not in allowed:
        raise HTTPException(status_code=403, detail="No access to this group")
    return group


def remove_staff_from_group(db: Session, org_id: UUID, staff_id: UUID, group_id: UUID) -> None:
    scoped_get(db, Staff, org_id, staff_id)
    scoped_get(db, Group, org_id, group_id)
    item = db.scalar(select(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
        GroupStaff.group_id == group_id,
    ))
    if item is None:
        return
    db.delete(item)
    db.commit()
