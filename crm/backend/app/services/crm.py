import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Attendance, AttendanceStatus, Contact, CrmStatus, Enrollment, EnrollmentStatus, Group, GroupSchedule, GroupStaff, LessonSession, LessonStatus, Location, Organization, OrganizationMembership, Payment, PaymentMethod, PaymentStatus, Staff, StaffLocation, StaffRole, Student, StudentContact, StudentStatus, StudentSubscription, SubscriptionPlan, SubscriptionStatus, TrialLesson, User
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


def create_payment(db: Session, org_id: UUID, data) -> Payment:
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
        due_date=data.due_date,
        note=data.note,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    item.plan_id = subscription.plan_id if data.subscription_id is not None else None
    return item


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
    return rows


def mark_payment_paid(db: Session, org_id: UUID, payment_id: UUID, method: PaymentMethod, paid_at: datetime | None = None) -> Payment:
    payment = scoped_get(db, Payment, org_id, payment_id)
    if payment.status == PaymentStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Cancelled payment cannot be marked as paid")
    payment.status = PaymentStatus.PAID
    payment.method = method
    payment.paid_at = paid_at or datetime.now(timezone.utc)
    db.commit()
    db.refresh(payment)
    if payment.subscription_id is not None:
        subscription = scoped_get(db, StudentSubscription, org_id, payment.subscription_id)
        payment.plan_id = subscription.plan_id
    else:
        payment.plan_id = None
    return payment


def payment_summary(db: Session, org_id: UUID) -> dict:
    rows = list(db.scalars(select(Payment).where(Payment.organization_id == org_id)))
    today = date.today()
    paid = [row for row in rows if row.status == PaymentStatus.PAID]
    pending = [row for row in rows if row.status == PaymentStatus.PENDING]
    overdue = [row for row in pending if row.due_date is not None and row.due_date < today]
    return {
        "paid_minor": sum(row.amount_minor for row in paid),
        "pending_minor": sum(row.amount_minor for row in pending),
        "overdue_minor": sum(row.amount_minor for row in overdue),
        "paid_count": len(paid),
        "pending_count": len(pending),
        "overdue_count": len(overdue),
    }


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
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "source": student.source,
            "crm_status": student.crm_status,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "latest_trial_id": trial.id if trial else None,
            "latest_trial_at": trial.starts_at if trial else None,
            "recommended_level": trial.recommended_level if trial else None,
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
