import hashlib
import re
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.core import Attendance, AttendanceStatus, AuditEvent, Contact, CrmStatus, Enrollment, EnrollmentStatus, Group, GroupSchedule, GroupStaff, LessonSession, LessonStatus, Location, Organization, OrganizationMembership, Payment, PaymentMethod, PaymentReminder, PaymentStatus, PaymentTransaction, PublicIntakeThrottle, Staff, StaffLocation, StaffRole, Student, StudentAvailability, StudentContact, StudentStatus, StudentSubscription, SubscriptionPause, SubscriptionPlan, SubscriptionStatus, SubscriptionUsage, MakeupCredit, TrialLesson, TrialStatus, User
from app.schemas import ContactCreate, EnrollmentCreate, GroupCreate, GroupUpdate, IntakeCreate, LeadDetailsUpdate, LocationCreate, OrganizationCreate, StudentCreate, TrialLessonCreate
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
    if digits.startswith("380") and len(digits) == 12:
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 10:
        national = digits[1:]
    elif len(digits) == 9:
        national = digits
    else:
        raise HTTPException(status_code=422, detail="Вкажіть український номер у форматі +380 XX XXX XX XX")

    if not re.fullmatch(r"[3-9]\d{8}", national):
        raise HTTPException(status_code=422, detail="Некоректний номер телефону України")
    return "+380" + national


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
    return list(db.scalars(
        select(Location)
        .where(Location.organization_id == org_id, Location.is_active.is_(True))
        .order_by(Location.name)
    ))


def delete_location(
    db: Session,
    org_id: UUID,
    location_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    location = scoped_get(db, Location, org_id, location_id)

    group = db.scalar(select(Group.id).where(
        Group.organization_id == org_id,
        Group.location_id == location.id,
    ).limit(1))
    if group is not None:
        raise HTTPException(
            status_code=409,
            detail="Цю локацію використовує група. Спочатку змініть локацію в групі або видаліть порожню групу.",
        )

    lesson = db.scalar(select(LessonSession.id).where(
        LessonSession.organization_id == org_id,
        LessonSession.location_id == location.id,
    ).limit(1))
    if lesson is not None:
        raise HTTPException(
            status_code=409,
            detail="Для цієї локації вже є заняття в історії або розкладі. Щоб не втратити дані, її видалити не можна.",
        )

    trial = db.scalar(select(TrialLesson.id).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.location_id == location.id,
    ).limit(1))
    if trial is not None:
        raise HTTPException(
            status_code=409,
            detail="Для цієї локації вже є пробні заняття. Щоб не втратити історію, її видалити не можна.",
        )

    staff_link = db.scalar(select(StaffLocation.id).where(
        StaffLocation.organization_id == org_id,
        StaffLocation.location_id == location.id,
    ).limit(1))
    if staff_link is not None:
        raise HTTPException(
            status_code=409,
            detail="Ця локація призначена працівнику. Спочатку приберіть її в картці працівника.",
        )

    student_preference = db.scalar(select(Student.id).where(
        Student.organization_id == org_id,
        Student.preferred_location_id == location.id,
    ).limit(1))
    if student_preference is not None:
        raise HTTPException(
            status_code=409,
            detail="Ця локація вказана в побажаннях учня. Спочатку змініть бажану локацію в картці учня.",
        )

    record_audit(
        db,
        org_id,
        "location",
        location.id,
        "location.deleted",
        {"name": location.name},
        actor_user_id=actor_user_id,
    )
    db.delete(location)
    db.commit()


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


def delete_student(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    student = scoped_get(db, Student, org_id, student_id)

    enrollment = db.scalar(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
    ).limit(1))
    if enrollment is not None:
        raise HTTPException(
            status_code=409,
            detail="Учень уже був зарахований до групи. Щоб не втратити історію навчання, видалити його не можна — використайте «Архів».",
        )

    completed_trial = db.scalar(select(TrialLesson.id).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.student_id == student.id,
        TrialLesson.status == TrialStatus.COMPLETED,
    ).limit(1))
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
        history = db.scalar(select(model.id).where(
            model.organization_id == org_id,
            model.student_id == student.id,
        ).limit(1))
        if history is not None:
            raise HTTPException(
                status_code=409,
                detail=f"{reason} Щоб не втратити історію учня, видалення заблоковано — використайте «Архів».",
            )

    # Draft/pre-enrollment data can be safely cleaned up for an accidentally created student.
    db.execute(delete(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student.id,
    ))
    db.execute(delete(StudentContact).where(
        StudentContact.organization_id == org_id,
        StudentContact.student_id == student.id,
    ))
    db.execute(delete(TrialLesson).where(
        TrialLesson.organization_id == org_id,
        TrialLesson.student_id == student.id,
    ))
    db.flush()

    record_audit(
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
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
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
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
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


def update_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    data: GroupUpdate,
    actor_user_id: UUID | None = None,
) -> Group:
    group = scoped_get(db, Group, org_id, group_id)
    if data.location_id is not None:
        scoped_get(db, Location, org_id, data.location_id)

    enrolled_count = len(list(db.scalars(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    ))))
    if data.capacity < enrolled_count:
        raise HTTPException(
            status_code=422,
            detail=f"Місткість групи не може бути меншою за кількість учасників ({enrolled_count}).",
        )

    group.name = data.name
    group.location_id = data.location_id
    group.capacity = data.capacity
    group.min_age = data.min_age
    group.max_age = data.max_age

    existing_schedules = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
    )))
    schedules_by_key = {(item.weekday, item.start_time): item for item in existing_schedules}
    desired_keys: set[tuple[int, time]] = set()

    for slot in data.schedule_slots:
        slot_time = time.fromisoformat(slot.start_time)
        key = (slot.weekday, slot_time)
        desired_keys.add(key)
        existing = schedules_by_key.get(key)
        if existing is None:
            db.add(GroupSchedule(
                organization_id=org_id,
                group_id=group.id,
                weekday=slot.weekday,
                start_time=slot_time,
                duration_minutes=slot.duration_minutes,
                is_active=True,
            ))
        else:
            existing.duration_minutes = slot.duration_minutes
            existing.is_active = True

    for existing in existing_schedules:
        if (existing.weekday, existing.start_time) not in desired_keys:
            existing.is_active = False

    record_audit(
        db,
        org_id,
        "group",
        group.id,
        "group.updated",
        {
            "name": group.name,
            "location_id": str(group.location_id) if group.location_id else None,
            "capacity": group.capacity,
            "schedule_slots": [
                {
                    "weekday": slot.weekday,
                    "start_time": slot.start_time,
                    "duration_minutes": slot.duration_minutes,
                }
                for slot in data.schedule_slots
            ],
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(group)
    return group


def delete_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    group = scoped_get(db, Group, org_id, group_id)

    enrollment = db.scalar(select(Enrollment.id).where(
        Enrollment.organization_id == org_id,
        Enrollment.group_id == group.id,
    ).limit(1))
    if enrollment is not None:
        raise HTTPException(
            status_code=409,
            detail="У цій групі є або були учні. Щоб не втратити історію навчання, таку групу видалити не можна.",
        )

    subscription = db.scalar(select(StudentSubscription.id).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.group_id == group.id,
    ).limit(1))
    if subscription is not None:
        raise HTTPException(
            status_code=409,
            detail="Ця група вже використовується в абонементах. Щоб не втратити фінансову історію, її видалити не можна.",
        )

    lessons = list(db.scalars(select(LessonSession).where(
        LessonSession.organization_id == org_id,
        LessonSession.group_id == group.id,
    )))
    completed_lesson = next((lesson for lesson in lessons if lesson.status == LessonStatus.COMPLETED), None)
    if completed_lesson is not None:
        raise HTTPException(
            status_code=409,
            detail="У цієї групи вже є проведене заняття. Щоб не втратити історію, таку групу видалити не можна.",
        )

    lesson_ids = [lesson.id for lesson in lessons]
    if lesson_ids:
        attendance = db.scalar(select(Attendance.id).where(
            Attendance.organization_id == org_id,
            Attendance.session_id.in_(lesson_ids),
        ).limit(1))
        if attendance is not None:
            raise HTTPException(
                status_code=409,
                detail="У заняттях цієї групи вже є відмітки відвідування. Щоб не втратити історію, групу видалити не можна.",
            )

        usage = db.scalar(select(SubscriptionUsage.id).where(
            SubscriptionUsage.organization_id == org_id,
            SubscriptionUsage.session_id.in_(lesson_ids),
        ).limit(1))
        if usage is not None:
            raise HTTPException(
                status_code=409,
                detail="Заняття цієї групи вже враховані в абонементах. Щоб не втратити історію, групу видалити не можна.",
            )

        makeup = db.scalar(select(MakeupCredit.id).where(
            MakeupCredit.organization_id == org_id,
            (MakeupCredit.original_session_id.in_(lesson_ids) | MakeupCredit.target_session_id.in_(lesson_ids)),
        ).limit(1))
        if makeup is not None:
            raise HTTPException(
                status_code=409,
                detail="Із заняттями цієї групи пов’язане відпрацювання. Спочатку завершіть або приберіть його.",
            )

    # A mistakenly created empty group may still have generated lesson placeholders.
    # If they contain no real history, remove those drafts together with the group.
    if lesson_ids:
        db.execute(delete(LessonSession).where(
            LessonSession.organization_id == org_id,
            LessonSession.group_id == group.id,
        ))

    db.execute(delete(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
    ))
    db.execute(delete(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.group_id == group.id,
    ))
    db.flush()

    record_audit(
        db,
        org_id,
        "group",
        group.id,
        "group.deleted",
        {
            "name": group.name,
            "removed_empty_lesson_placeholders": len(lesson_ids),
        },
        actor_user_id=actor_user_id,
    )
    db.delete(group)
    db.commit()

def list_groups(db: Session, org_id: UUID) -> list[Group]:
    return list(db.scalars(select(Group).where(Group.organization_id == org_id, Group.is_active.is_(True)).order_by(Group.name)))


def create_enrollment(
    db: Session,
    org_id: UUID,
    data: EnrollmentCreate,
    actor_user_id: UUID | None = None,
) -> Enrollment:
    student = scoped_get(db, Student, org_id, data.student_id)
    group = scoped_get(db, Group, org_id, data.group_id)
    previous_crm_status = student.crm_status

    ensure_group_capacity(db, org_id, group, data.student_id)
    existing = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.group_id == group.id,
        Enrollment.status.in_([EnrollmentStatus.ACTIVE, EnrollmentStatus.PAUSED]),
    ))
    if existing is not None:
        return existing

    group_slots = list(db.scalars(select(GroupSchedule).where(
        GroupSchedule.organization_id == org_id,
        GroupSchedule.group_id == group.id,
        GroupSchedule.is_active.is_(True),
    ).order_by(GroupSchedule.weekday, GroupSchedule.start_time)))
    windows = list(db.scalars(select(StudentAvailability).where(
        StudentAvailability.organization_id == org_id,
        StudentAvailability.student_id == student.id,
    )))
    match = evaluate_schedule_match(group_slots, windows, group.location_id, student.preferred_location_id)
    note = enrollment_schedule_note(match, group_slots, windows)

    item = Enrollment(
        organization_id=org_id,
        student_id=student.id,
        group_id=group.id,
        started_at=data.started_at or date.today(),
        schedule_match=match.status,
        schedule_note=note,
    )
    db.add(item)
    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "student.enrolled",
        {
            "group_id": str(group.id),
            "group_name": group.name,
            "schedule_match": match.status,
            "schedule_note": note,
            "previous_crm_status": previous_crm_status.value,
            "skipped_funnel_stages": previous_crm_status not in {CrmStatus.TRIAL_COMPLETED, CrmStatus.WAITING_FOR_GROUP},
        },
        actor_user_id=actor_user_id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Student is already enrolled in this group") from exc
    db.refresh(item)
    return item


def find_intake_phone_duplicates(
    db: Session,
    org_id: UUID,
    child_first_name: str,
    child_age: int,
    phone: str,
    child_phone: str | None = None,
) -> list[dict]:
    parent_phone = normalize_phone(phone)
    normalized_child_phone = normalize_phone(child_phone) if child_phone else None
    normalized_name = child_first_name.strip().casefold()
    matches: dict[UUID, dict] = {}

    direct_numbers = {value for value in (parent_phone, normalized_child_phone) if value}
    if direct_numbers:
        direct_students = list(db.scalars(select(Student).where(
            Student.organization_id == org_id,
            Student.phone.in_(direct_numbers),
        )))
        for student in direct_students:
            matched_phone = student.phone or parent_phone
            matches[student.id] = {
                "student": student,
                "matched_phone": matched_phone,
                "matched_as": "student",
                "likely_same_student": True,
            }

    contact_rows = db.execute(
        select(Student, Contact)
        .join(StudentContact, StudentContact.student_id == Student.id)
        .join(Contact, Contact.id == StudentContact.contact_id)
        .where(
            Student.organization_id == org_id,
            StudentContact.organization_id == org_id,
            Contact.organization_id == org_id,
            Contact.phone.in_(direct_numbers),
        )
    ).all() if direct_numbers else []

    for student, contact in contact_rows:
        same_child = (
            student.first_name.strip().casefold() == normalized_name
            and student.age_at_inquiry == child_age
        )
        existing = matches.get(student.id)
        if existing:
            existing["matched_as"] = "student_and_contact"
            existing["likely_same_student"] = existing["likely_same_student"] or same_child
            existing["contact"] = contact
        else:
            matches[student.id] = {
                "student": student,
                "contact": contact,
                "matched_phone": contact.phone,
                "matched_as": "contact",
                "likely_same_student": same_child,
            }

    result: list[dict] = []
    for item in matches.values():
        student = item["student"]
        contact = item.get("contact")
        if contact is None:
            contact = db.scalar(
                select(Contact)
                .join(StudentContact, StudentContact.contact_id == Contact.id)
                .where(
                    StudentContact.organization_id == org_id,
                    StudentContact.student_id == student.id,
                    Contact.organization_id == org_id,
                )
                .order_by(StudentContact.is_primary.desc(), Contact.created_at)
                .limit(1)
            )
        result.append({
            "student_id": student.id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "age": student.age_at_inquiry,
            "crm_status": student.crm_status,
            "student_status": student.student_status,
            "student_phone": student.phone,
            "contact_name": contact.full_name if contact else None,
            "contact_phone": contact.phone if contact else None,
            "matched_phone": item["matched_phone"],
            "matched_as": item["matched_as"],
            "likely_same_student": item["likely_same_student"],
        })
    return sorted(result, key=lambda item: (not item["likely_same_student"], item["first_name"].casefold()))


def _append_repeat_intake_note(organization: Organization, student: Student, data: IntakeCreate) -> None:
    try:
        local_tz = ZoneInfo(organization.timezone)
    except Exception:
        local_tz = timezone.utc
    local_now = datetime.now(timezone.utc).astimezone(local_tz)
    source_label = "через сайт" if data.source == "website" else f"· {data.source}"
    lines = [f"Повторне звернення {source_label} — {local_now.strftime('%d.%m.%Y %H:%M')}"]
    if data.comment and data.comment.strip():
        lines.append(f"Коментар: {data.comment.strip()}")
    repeat_note = "\n".join(lines)
    student.notes = f"{student.notes.rstrip()}\n\n{repeat_note}" if student.notes and student.notes.strip() else repeat_note


def create_intake(db: Session, organization: Organization, data: IntakeCreate, actor_user_id: UUID | None = None, record_repeat: bool = False) -> tuple[Student, Contact]:
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
        if data.child_last_name and not existing_student.last_name:
            existing_student.last_name = data.child_last_name
        if data.child_phone and not existing_student.phone:
            existing_student.phone = data.child_phone
        if record_repeat:
            _append_repeat_intake_note(organization, existing_student, data)
        elif data.comment and not existing_student.notes:
            existing_student.notes = data.comment
        if data.source and not existing_student.source:
            existing_student.source = data.source
        record_audit(
            db,
            organization.id,
            "student",
            existing_student.id,
            "lead.duplicate_intake",
            {"source": data.source, "contact_id": str(contact.id), "repeat": record_repeat, "comment": data.comment},
            actor_user_id=actor_user_id,
        )
        db.commit()
        db.refresh(existing_student)
        db.refresh(contact)
        return existing_student, contact

    student = Student(
        organization_id=organization.id,
        first_name=data.child_first_name.strip(),
        last_name=data.child_last_name,
        phone=data.child_phone,
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


def update_lead_details(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    data: LeadDetailsUpdate,
    actor_user_id: UUID | None = None,
) -> Student:
    student = scoped_get(db, Student, org_id, student_id)

    primary_link = db.scalar(
        select(StudentContact)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == student.id,
        )
        .order_by(StudentContact.is_primary.desc(), StudentContact.id)
    )
    contact = scoped_get(db, Contact, org_id, primary_link.contact_id) if primary_link is not None else None

    before = {
        "child_name": " ".join(part for part in [student.first_name, student.last_name] if part),
        "child_phone": student.phone,
        "child_age": student.age_at_inquiry,
        "contact_name": contact.full_name if contact else None,
        "contact_phone": contact.phone if contact else None,
        "source": student.source,
        "comment": student.notes,
    }

    student.first_name = data.child_first_name
    student.last_name = data.child_last_name
    student.phone = data.child_phone
    student.age_at_inquiry = data.child_age
    student.source = data.source
    student.notes = data.comment

    if contact is None:
        contact = Contact(
            organization_id=org_id,
            full_name=data.contact_name,
            phone=data.phone,
        )
        db.add(contact)
        db.flush()
        primary_link = StudentContact(
            organization_id=org_id,
            student_id=student.id,
            contact_id=contact.id,
            relation="parent_or_guardian",
            is_primary=True,
        )
        db.add(primary_link)
    else:
        contact.full_name = data.contact_name
        contact.phone = data.phone

    after = {
        "child_name": " ".join(part for part in [student.first_name, student.last_name] if part),
        "child_phone": student.phone,
        "child_age": student.age_at_inquiry,
        "contact_name": contact.full_name,
        "contact_phone": contact.phone,
        "source": student.source,
        "comment": student.notes,
    }
    changed_fields = [key for key, value in after.items() if before.get(key) != value]

    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "lead.details_updated",
        {
            "changed_fields": changed_fields,
            "source": student.source,
            "comment_changed": before["comment"] != after["comment"],
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(student)
    return student


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


def defer_lead(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    deferred_until: datetime | None,
    reason: str | None,
    note: str | None,
    actor_user_id: UUID | None = None,
) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    if student.student_status != StudentStatus.PROSPECT:
        raise HTTPException(status_code=409, detail="Відкласти можна лише активну заявку, не зарахованого учня.")

    if deferred_until is not None:
        now = datetime.now(timezone.utc)
        value = deferred_until if deferred_until.tzinfo else deferred_until.replace(tzinfo=timezone.utc)
        if value <= now:
            raise HTTPException(status_code=422, detail="Дата повернення має бути в майбутньому.")
        student.deferred_until = deferred_until
        student.deferred_reason = reason
        student.deferred_note = note
        student.next_contact_at = deferred_until
        event_type = "lead.deferred"
        payload = {"deferred_until": deferred_until.isoformat(), "reason": reason, "note": note}
    else:
        student.deferred_until = None
        student.deferred_reason = None
        student.deferred_note = None
        student.next_contact_at = None
        event_type = "lead.deferred_cleared"
        payload = {}

    record_audit(db, org_id, "student", student.id, event_type, payload, actor_user_id=actor_user_id)
    db.commit()
    db.refresh(student)
    return student


def update_lead_outcome(db: Session, org_id: UUID, student_id: UUID, data, actor_user_id: UUID | None = None) -> Student:
    student = scoped_get(db, Student, org_id, student_id)
    student.crm_status = data.crm_status
    student.next_contact_at = data.next_contact_at
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None

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
            "student_phone": student.phone,
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


def enroll_student_without_group(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None = None,
) -> Student:
    student = scoped_get(db, Student, org_id, student_id)

    active_enrollment = db.scalar(select(Enrollment).where(
        Enrollment.organization_id == org_id,
        Enrollment.student_id == student.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
    ))
    if active_enrollment is not None:
        raise HTTPException(status_code=409, detail="Student is already enrolled in a group")

    student.crm_status = CrmStatus.ENROLLED
    student.student_status = StudentStatus.ACTIVE
    student.next_contact_at = None
    student.deferred_until = None
    student.deferred_reason = None
    student.deferred_note = None
    student.lead_close_reason = None
    student.lead_close_note = None
    record_audit(
        db,
        org_id,
        "student",
        student.id,
        "student.enrolled_without_group",
        {"group_id": None, "location_id": None},
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(student)
    return student


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
    finance_visible = role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER, StaffRole.ACCOUNTANT}
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
            lessons_used = None
            lessons_remaining = None
            if latest_subscription and plan:
                usage_summary = subscription_usage_summary(db, org_id, latest_subscription)
                lessons_used = usage_summary["used_lessons"]
                lessons_remaining = usage_summary["remaining_lessons"]
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
            elif latest_subscription and latest_subscription.status == SubscriptionStatus.ACTIVE and (latest_subscription.ends_on is None or latest_subscription.ends_on >= today):
                billing_status = "current"
            else:
                billing_status = "no_plan"

            billing = {
                "status": billing_status,
                "plan_name": plan.name if plan else None,
                "lessons_used": lessons_used,
                "lessons_included": latest_subscription.lessons_included if latest_subscription else (plan.lessons_included if plan else None),
                "lessons_remaining": lessons_remaining,
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
            "student_phone": student.phone,
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


def _comparable_dt(value: datetime, timezone_name: str) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo(timezone_name))
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _lesson_conflict_reason(
    db: Session,
    org_id: UUID,
    group: Group,
    location_id: UUID | None,
    starts_at: datetime,
    duration_minutes: int,
) -> str | None:
    organization = require_organization(db, org_id)
    start = _comparable_dt(starts_at, organization.timezone)
    end = start + timedelta(minutes=duration_minutes)
    sessions = list(db.scalars(
        select(LessonSession).where(
            LessonSession.organization_id == org_id,
            LessonSession.status != LessonStatus.CANCELLED,
        )
    ))
    new_staff_ids = set(db.scalars(select(GroupStaff.staff_id).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.group_id == group.id,
    )))

    for existing in sessions:
        existing_start = _comparable_dt(existing.starts_at, organization.timezone)
        existing_end = existing_start + timedelta(minutes=existing.duration_minutes)
        if not (start < existing_end and end > existing_start):
            continue

        existing_group = scoped_get(db, Group, org_id, existing.group_id)
        same_group = existing.group_id == group.id
        same_location = bool(location_id and existing.location_id and location_id == existing.location_id)
        shared_staff = False
        if existing.group_id != group.id and new_staff_ids:
            existing_staff_ids = set(db.scalars(select(GroupStaff.staff_id).where(
                GroupStaff.organization_id == org_id,
                GroupStaff.group_id == existing.group_id,
            )))
            shared_staff = bool(new_staff_ids & existing_staff_ids)

        if same_group or same_location or shared_staff:
            reasons = []
            if same_group:
                reasons.append("ця група вже має заняття")
            if same_location:
                reasons.append("локація зайнята")
            if shared_staff:
                reasons.append("викладач зайнятий")
            return (
                f"Час зайнятий: {existing_group.name} "
                f"{existing_start.strftime('%d.%m %H:%M')}–{existing_end.strftime('%H:%M')} "
                f"({', '.join(reasons)}). Оберіть інший час."
            )
    return None


def materialize_recurring_lesson_sessions(
    db: Session,
    org_id: UUID,
    weeks_back: int = 0,
    weeks_forward: int = 8,
) -> int:
    """Create concrete lesson sessions from active recurring group schedules.

    This is intentionally idempotent: an existing lesson for the same group
    and exact start time is reused, so manual sessions and previously generated
    sessions are never duplicated.
    """
    organization = db.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    try:
        tz = ZoneInfo(organization.timezone)
    except Exception:
        tz = timezone.utc

    local_today = datetime.now(tz).date()
    current_monday = local_today - timedelta(days=local_today.weekday())
    window_start = current_monday - timedelta(weeks=weeks_back)
    window_end = current_monday + timedelta(weeks=weeks_forward + 1) - timedelta(days=1)

    schedules = list(db.scalars(
        select(GroupSchedule)
        .join(Group, Group.id == GroupSchedule.group_id)
        .where(
            GroupSchedule.organization_id == org_id,
            GroupSchedule.is_active.is_(True),
            Group.organization_id == org_id,
            Group.is_active.is_(True),
        )
        .order_by(GroupSchedule.group_id, GroupSchedule.weekday, GroupSchedule.start_time)
    ))
    if not schedules:
        return 0

    groups = {
        group.id: group
        for group in db.scalars(
            select(Group).where(
                Group.organization_id == org_id,
                Group.id.in_({slot.group_id for slot in schedules}),
            )
        )
    }

    created = 0
    for slot in schedules:
        group = groups.get(slot.group_id)
        if group is None:
            continue

        first_date = window_start + timedelta(days=slot.weekday)
        current_date = first_date
        while current_date <= window_end:
            local_start = datetime.combine(current_date, slot.start_time).replace(tzinfo=tz)
            starts_at = local_start.astimezone(timezone.utc)
            exists = db.scalar(
                select(LessonSession.id).where(
                    LessonSession.organization_id == org_id,
                    LessonSession.group_id == group.id,
                    LessonSession.starts_at == starts_at,
                )
            )
            if exists is None:
                db.add(LessonSession(
                    organization_id=org_id,
                    group_id=group.id,
                    location_id=group.location_id,
                    starts_at=starts_at,
                    duration_minutes=slot.duration_minutes,
                    topic=None,
                    notes=None,
                    status=LessonStatus.SCHEDULED,
                ))
                created += 1
            current_date += timedelta(days=7)

    if created:
        db.commit()
    return created


def create_lesson_session(db: Session, org_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    group = ensure_group_access(db, org_id, user_id, role, data.group_id)
    location_id = data.location_id if data.location_id is not None else group.location_id
    if location_id is not None:
        scoped_get(db, Location, org_id, location_id)
    conflict = _lesson_conflict_reason(db, org_id, group, location_id, data.starts_at, data.duration_minutes)
    if conflict:
        raise HTTPException(status_code=409, detail=conflict)
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
    materialize_recurring_lesson_sessions(db, org_id)
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = select(LessonSession).where(LessonSession.organization_id == org_id)
    if group_id is not None:
        ensure_group_access(db, org_id, user_id, role, group_id)
        stmt = stmt.where(LessonSession.group_id == group_id)
    elif allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(LessonSession.group_id.in_(allowed))
    rows = list(db.scalars(stmt.order_by(LessonSession.starts_at)))
    if not rows:
        return rows
    counts = {item.id: {"present": 0, "absent": 0, "late": 0, "excused": 0, "total": 0} for item in rows}
    for mark in db.scalars(select(Attendance).where(
        Attendance.organization_id == org_id,
        Attendance.session_id.in_(list(counts)),
    )):
        bucket = counts.get(mark.session_id)
        if bucket is None:
            continue
        key = mark.status.value
        if key in bucket:
            bucket[key] += 1
        bucket["total"] += 1
    for item in rows:
        summary = counts[item.id]
        item.attendance_present = summary["present"]
        item.attendance_absent = summary["absent"]
        item.attendance_late = summary["late"]
        item.attendance_excused = summary["excused"]
        item.attendance_total = summary["total"]
    return rows


def update_lesson_session(db: Session, org_id: UUID, session_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    item = scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, item.group_id)
    changes = data.model_dump(exclude_unset=True)
    before = {"topic": item.topic, "notes": item.notes}
    if "topic" in changes:
        item.topic = changes["topic"]
    if "notes" in changes:
        item.notes = changes["notes"]
    record_audit(
        db,
        org_id,
        "lesson_session",
        item.id,
        "lesson.details_updated",
        {"before": before, "after": {"topic": item.topic, "notes": item.notes}, "group_id": str(item.group_id)},
        actor_user_id=user_id,
    )
    db.commit()
    db.refresh(item)
    return item


def _eligible_subscription_for_session(db: Session, org_id: UUID, student_id: UUID, session: LessonSession) -> tuple[StudentSubscription, SubscriptionPlan] | None:
    organization = require_organization(db, org_id)
    lesson_date = _comparable_dt(session.starts_at, organization.timezone).date()
    rows = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student_id,
        StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
    ).order_by(StudentSubscription.starts_on, StudentSubscription.created_at)))
    for subscription in rows:
        if subscription.group_id is not None and subscription.group_id != session.group_id:
            continue
        if lesson_date < subscription.starts_on:
            continue
        plan = scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
        summary = subscription_usage_summary(db, org_id, subscription)
        if subscription.ends_on is not None and plan.end_rule in {"date", "whichever_first"} and lesson_date > subscription.ends_on:
            continue
        included = subscription.lessons_included
        if included is None and subscription.period_days is None:
            included = plan.lessons_included
        if included is not None and summary["remaining_lessons"] == 0:
            continue
        return subscription, plan
    return None


def _attendance_should_consume(plan: SubscriptionPlan, status: AttendanceStatus, explicit: bool | None) -> bool:
    if status == AttendanceStatus.PRESENT:
        return True
    if status == AttendanceStatus.LATE:
        return plan.late_rule == "consume"
    if status == AttendanceStatus.EXCUSED:
        return plan.excused_rule == "consume"
    if status == AttendanceStatus.ABSENT:
        if plan.absent_rule == "consume":
            return True
        if plan.absent_rule == "dont_consume":
            return False
        return bool(explicit)
    return False


def _sync_makeup_credit(db: Session, org_id: UUID, session: LessonSession, student_id: UUID, plan: SubscriptionPlan | None, status: AttendanceStatus) -> None:
    existing = db.scalar(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.original_session_id == session.id,
        MakeupCredit.student_id == student_id,
    ))
    if status == AttendanceStatus.EXCUSED and plan is not None and plan.excused_rule == "makeup":
        expires_on = None
        if plan.makeup_expiry_days:
            organization = require_organization(db, org_id)
            expires_on = _comparable_dt(session.starts_at, organization.timezone).date() + timedelta(days=plan.makeup_expiry_days)
        if existing is None:
            db.add(MakeupCredit(organization_id=org_id, student_id=student_id, original_session_id=session.id, status="pending", expires_on=expires_on))
        elif existing.status == "cancelled":
            existing.status = "pending"
            existing.expires_on = expires_on
    elif existing is not None and existing.status == "pending":
        existing.status = "cancelled"


def _complete_oldest_makeup(db: Session, org_id: UUID, student_id: UUID, target_session_id: UUID) -> bool:
    today = date.today()
    credits = list(db.scalars(select(MakeupCredit).where(
        MakeupCredit.organization_id == org_id,
        MakeupCredit.student_id == student_id,
        MakeupCredit.status == "pending",
        MakeupCredit.original_session_id != target_session_id,
    ).order_by(MakeupCredit.created_at)))
    credit = next((item for item in credits if item.expires_on is None or item.expires_on >= today), None)
    if credit is None:
        return False
    credit.status = "completed"
    credit.target_session_id = target_session_id
    credit.completed_at = datetime.now(timezone.utc)
    return True


def _renew_after_last_lesson(db: Session, org_id: UUID, subscription: StudentSubscription, plan: SubscriptionPlan, session: LessonSession, actor_user_id: UUID | None) -> None:
    included = subscription.lessons_included
    if included is None and subscription.period_days is None:
        included = plan.lessons_included
    if not subscription.auto_renew or plan.renewal_trigger != "last_lesson" or included is None:
        return
    if subscription_usage_summary(db, org_id, subscription)["remaining_lessons"] != 0:
        return
    if not plan.is_active:
        return
    existing = db.scalar(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.renewal_of_id == subscription.id,
        StudentSubscription.status != SubscriptionStatus.CANCELLED,
    ))
    if existing is not None:
        return
    organization = require_organization(db, org_id)
    after_date = _comparable_dt(session.starts_at, organization.timezone).date() + timedelta(days=1)
    next_start = _first_planned_lesson_date(db, org_id, subscription.group_id, after_date)
    available_credit = max(0, subscription.credit_minor)
    applied_credit = min(available_credit, plan.price_minor)
    carry_credit = max(0, available_credit - applied_credit)
    amount_due = max(0, plan.price_minor - applied_credit)
    next_subscription = StudentSubscription(
        organization_id=org_id, student_id=subscription.student_id, plan_id=plan.id, group_id=subscription.group_id,
        status=SubscriptionStatus.ACTIVE, starts_on=next_start, ends_on=_subscription_end_date(next_start, plan.period_days),
        price_minor=plan.price_minor, period_days=plan.period_days, lessons_included=plan.lessons_included,
        lesson_unit_price_minor=_lesson_unit_price(plan.price_minor, plan.lessons_included),
        credit_minor=carry_credit, discount_minor=0, discount_label=None, auto_renew=True, renewal_of_id=subscription.id,
    )
    db.add(next_subscription)
    db.flush()
    payment = Payment(
        organization_id=org_id, student_id=subscription.student_id, subscription_id=next_subscription.id,
        amount_minor=amount_due, currency=organization.currency, due_date=next_start,
        note=f"{plan.name} · продовження після останнього заняття",
        status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
        paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
    )
    db.add(payment)
    subscription.credit_minor = 0
    subscription.status = SubscriptionStatus.EXPIRED
    record_audit(db, org_id, "student", subscription.student_id, "subscription.renewed_after_last_lesson", {
        "previous_subscription_id": str(subscription.id), "subscription_id": str(next_subscription.id),
        "payment_id": str(payment.id), "session_id": str(session.id),
        "tariff_price_minor": plan.price_minor, "credit_applied_minor": applied_credit,
        "amount_due_minor": amount_due, "credit_carried_minor": carry_credit,
    }, actor_user_id=actor_user_id)


def _sync_attendance_usage(db: Session, org_id: UUID, session: LessonSession, attendance: Attendance, explicit_consume: bool | None, actor_user_id: UUID | None) -> None:
    current = db.scalar(select(SubscriptionUsage).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.session_id == session.id,
        SubscriptionUsage.student_id == attendance.student_id,
    ))
    eligible = _eligible_subscription_for_session(db, org_id, attendance.student_id, session)
    plan = eligible[1] if eligible else None
    _sync_makeup_credit(db, org_id, session, attendance.student_id, plan, attendance.status)

    # A pending excused absence is used before a new subscription lesson. This
    # lets a child work it off even after the original 30-day period ended.
    used_makeup = False
    if attendance.status in {AttendanceStatus.PRESENT, AttendanceStatus.LATE}:
        used_makeup = _complete_oldest_makeup(db, org_id, attendance.student_id, session.id)

    should_consume = bool(plan and not used_makeup and _attendance_should_consume(plan, attendance.status, explicit_consume))
    if should_consume and eligible is not None:
        subscription, plan = eligible
        if current is None:
            current = SubscriptionUsage(
                organization_id=org_id, subscription_id=subscription.id, student_id=attendance.student_id,
                session_id=session.id, attendance_id=attendance.id, units=1, source_status=attendance.status.value,
            )
            db.add(current)
            db.flush()
        else:
            current.subscription_id = subscription.id
            current.attendance_id = attendance.id
            current.source_status = attendance.status.value
        db.flush()
        _renew_after_last_lesson(db, org_id, subscription, plan, session, actor_user_id)
    elif current is not None:
        db.delete(current)
        db.flush()


def mark_attendance_bulk(db: Session, org_id: UUID, session_id: UUID, items, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[Attendance]:
    session = scoped_get(db, LessonSession, org_id, session_id)
    ensure_group_access(db, org_id, user_id, role, session.group_id)
    roster_ids = {item["student_id"] for item in group_roster(db, org_id, session.group_id, user_id, role)}
    submitted_ids = [item.student_id for item in items]
    if len(set(submitted_ids)) != len(submitted_ids):
        raise HTTPException(status_code=422, detail="Duplicate students in attendance payload")
    if not set(submitted_ids).issubset(roster_ids):
        raise HTTPException(status_code=409, detail="Відвідування можна відмічати лише для активних учнів цієї групи")

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
        db.flush()
        _sync_attendance_usage(db, org_id, session, row, getattr(mark, "consume_lesson", None), user_id)
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


def student_attendance_history(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
) -> list[dict]:
    scoped_get(db, Student, org_id, student_id)
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    stmt = (
        select(Attendance, LessonSession, Group)
        .join(LessonSession, LessonSession.id == Attendance.session_id)
        .join(Group, Group.id == LessonSession.group_id)
        .where(
            Attendance.organization_id == org_id,
            Attendance.student_id == student_id,
            LessonSession.organization_id == org_id,
            Group.organization_id == org_id,
        )
    )
    if allowed is not None:
        if not allowed:
            return []
        stmt = stmt.where(LessonSession.group_id.in_(allowed))
    rows = db.execute(stmt.order_by(LessonSession.starts_at.desc())).all()
    return [
        {
            "session_id": session.id,
            "group_id": session.group_id,
            "group_name": group.name,
            "starts_at": session.starts_at,
            "duration_minutes": session.duration_minutes,
            "topic": session.topic,
            "lesson_status": session.status,
            "status": attendance.status,
            "note": attendance.note,
        }
        for attendance, session, group in rows
    ]


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
    credit = max(0, net_paid - adjusted_amount)
    return {
        "adjusted_amount_minor": adjusted_amount,
        "paid_minor": paid_minor,
        "refunded_minor": refunded_minor,
        "net_paid_minor": net_paid,
        "balance_minor": balance,
        "credit_minor": credit,
        "transactions": transactions,
    }


def _sync_payment_state(db: Session, org_id: UUID, payment: Payment) -> dict:
    finance = payment_financials(db, org_id, payment)
    if payment.status != PaymentStatus.CANCELLED:
        if finance["adjusted_amount_minor"] == 0 and finance["net_paid_minor"] == 0 and finance["refunded_minor"] > 0:
            payment.status = PaymentStatus.REFUNDED
        elif finance["balance_minor"] == 0 and (finance["adjusted_amount_minor"] > 0 or finance["net_paid_minor"] > 0):
            payment.status = PaymentStatus.PAID
        else:
            payment.status = PaymentStatus.PENDING
    payment.adjusted_amount_minor = finance["adjusted_amount_minor"]
    payment.paid_minor = finance["paid_minor"]
    payment.refunded_minor = finance["refunded_minor"]
    payment.balance_minor = finance["balance_minor"]
    payment.credit_minor = finance["credit_minor"]
    return finance


def _attach_payment_financials(db: Session, org_id: UUID, payment: Payment) -> Payment:
    finance = payment_financials(db, org_id, payment)
    payment.adjusted_amount_minor = finance["adjusted_amount_minor"]
    payment.paid_minor = finance["paid_minor"]
    payment.refunded_minor = finance["refunded_minor"]
    payment.balance_minor = finance["balance_minor"]
    payment.credit_minor = finance["credit_minor"]
    return payment


def _subscription_end_date(starts_on: date, period_days: int | None) -> date | None:
    return starts_on + timedelta(days=period_days - 1) if period_days is not None else None


def _lesson_unit_price(price_minor: int, lessons_included: int | None) -> int | None:
    if lessons_included is None or lessons_included <= 0:
        return None
    return int(round(price_minor / lessons_included))


def _first_planned_lesson_date(
    db: Session,
    org_id: UUID,
    group_id: UUID | None,
    not_before: date,
) -> date:
    if group_id is None:
        return not_before
    materialize_recurring_lesson_sessions(db, org_id)
    organization = require_organization(db, org_id)
    try:
        tz = ZoneInfo(organization.timezone)
    except Exception:
        tz = timezone.utc
    candidates = list(db.scalars(
        select(LessonSession).where(
            LessonSession.organization_id == org_id,
            LessonSession.group_id == group_id,
            LessonSession.status != LessonStatus.CANCELLED,
        ).order_by(LessonSession.starts_at)
    ))
    for lesson in candidates:
        local_date = _comparable_dt(lesson.starts_at, organization.timezone).date()
        if local_date >= not_before:
            return local_date
    return not_before


def create_subscription_plan(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> SubscriptionPlan:
    require_organization(db, org_id)
    item = SubscriptionPlan(organization_id=org_id, **data.model_dump())
    db.add(item)
    db.flush()
    record_audit(
        db,
        org_id,
        "subscription_plan",
        item.id,
        "subscription_plan.created",
        {
            "name": item.name,
            "price_minor": item.price_minor,
            "period_days": item.period_days,
            "lessons_included": item.lessons_included,
            "is_active": item.is_active,
        },
        actor_user_id=actor_user_id,
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Тариф із такою назвою вже існує") from exc
    db.refresh(item)
    return item


def update_subscription_plan(
    db: Session,
    org_id: UUID,
    plan_id: UUID,
    data,
    actor_user_id: UUID | None = None,
) -> SubscriptionPlan:
    plan = scoped_get(db, SubscriptionPlan, org_id, plan_id)
    before = {
        "name": plan.name,
        "price_minor": plan.price_minor,
        "period_days": plan.period_days,
        "lessons_included": plan.lessons_included,
        "is_active": plan.is_active,
    }
    plan.name = data.name
    plan.price_minor = data.price_minor
    plan.period_days = data.period_days
    plan.lessons_included = data.lessons_included
    plan.is_active = data.is_active
    after = {
        "name": plan.name,
        "price_minor": plan.price_minor,
        "period_days": plan.period_days,
        "lessons_included": plan.lessons_included,
        "is_active": plan.is_active,
    }
    changed_fields = [key for key in after if before[key] != after[key]]
    if changed_fields:
        record_audit(
            db,
            org_id,
            "subscription_plan",
            plan.id,
            "subscription_plan.updated",
            {"before": before, "after": after, "changed_fields": changed_fields},
            actor_user_id=actor_user_id,
        )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Тариф із такою назвою вже існує") from exc
    db.refresh(plan)
    return plan


def list_subscription_plans(db: Session, org_id: UUID) -> list[SubscriptionPlan]:
    return list(db.scalars(
        select(SubscriptionPlan)
        .where(SubscriptionPlan.organization_id == org_id)
        .order_by(SubscriptionPlan.is_active.desc(), SubscriptionPlan.name)
    ))


def create_student_subscription(db: Session, org_id: UUID, data) -> StudentSubscription:
    student = scoped_get(db, Student, org_id, data.student_id)
    plan = scoped_get(db, SubscriptionPlan, org_id, data.plan_id)
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="Неактивний тариф не можна призначити новому абонементу")
    price_minor = data.price_minor if data.price_minor is not None else plan.price_minor
    if data.discount_minor > price_minor:
        raise HTTPException(status_code=422, detail="Знижка не може бути більшою за вартість тарифу")
    group_id = getattr(data, "group_id", None)
    starts_on = _first_planned_lesson_date(db, org_id, group_id, data.starts_on)
    item = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        group_id=group_id,
        starts_on=starts_on,
        ends_on=_subscription_end_date(starts_on, plan.period_days),
        price_minor=price_minor,
        period_days=plan.period_days,
        lessons_included=plan.lessons_included,
        lesson_unit_price_minor=_lesson_unit_price(max(0, price_minor - data.discount_minor), plan.lessons_included),
        credit_minor=0,
        discount_minor=data.discount_minor,
        discount_label=data.discount_label,
        auto_renew=getattr(data, "auto_renew", False),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def subscription_usage_summary(db: Session, org_id: UUID, subscription: StudentSubscription) -> dict:
    plan = scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
    included = subscription.lessons_included
    if included is None and subscription.period_days is None:
        # Legacy row created before tariff snapshots existed.
        included = plan.lessons_included
    used = db.scalar(select(func.coalesce(func.sum(SubscriptionUsage.units), 0)).where(
        SubscriptionUsage.organization_id == org_id,
        SubscriptionUsage.subscription_id == subscription.id,
    )) or 0
    remaining = max(0, included - int(used)) if included is not None else None
    return {"used_lessons": int(used), "remaining_lessons": remaining, "needs_renewal": remaining == 1 if remaining is not None else False}


def _attach_subscription_usage(db: Session, org_id: UUID, subscription: StudentSubscription) -> StudentSubscription:
    summary = subscription_usage_summary(db, org_id, subscription)
    subscription.used_lessons = summary["used_lessons"]
    subscription.remaining_lessons = summary["remaining_lessons"]
    subscription.needs_renewal = summary["needs_renewal"]
    return subscription


def list_student_subscriptions(db: Session, org_id: UUID, student_id: UUID | None = None) -> list[StudentSubscription]:
    stmt = select(StudentSubscription).where(StudentSubscription.organization_id == org_id)
    if student_id is not None:
        scoped_get(db, Student, org_id, student_id)
        stmt = stmt.where(StudentSubscription.student_id == student_id)
    rows = list(db.scalars(stmt.order_by(StudentSubscription.starts_on.desc())))
    return [_attach_subscription_usage(db, org_id, row) for row in rows]


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
    if starts_on < subscription.starts_on or (subscription.ends_on is not None and starts_on > subscription.ends_on):
        raise HTTPException(status_code=422, detail="Пауза має починатися в межах поточного абонемента")

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
    if subscription.ends_on is not None:
        subscription.ends_on = subscription.ends_on + timedelta(days=paused_days)
        subscription.status = SubscriptionStatus.ACTIVE if subscription.ends_on >= resumes_on else SubscriptionStatus.EXPIRED
    else:
        subscription.status = SubscriptionStatus.ACTIVE
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
        raise HTTPException(status_code=422, detail="Дата перевірки не може бути в минулому")

    resumed = _resume_due_pauses(db, org_id, today, actor_user_id)
    expired_rows = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.status == SubscriptionStatus.ACTIVE,
        StudentSubscription.ends_on.is_not(None),
        StudentSubscription.ends_on < today,
    )))
    for expired in expired_rows:
        open_pause = db.scalar(select(SubscriptionPause.id).where(
            SubscriptionPause.organization_id == org_id,
            SubscriptionPause.subscription_id == expired.id,
            SubscriptionPause.resumed_at.is_(None),
        ))
        if open_pause is None:
            expired.status = SubscriptionStatus.EXPIRED
    if expired_rows:
        db.flush()

    created_payment_ids: list[UUID] = []
    created_subscriptions = 0
    skipped_stale_subscriptions = 0

    candidates = list(db.scalars(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.auto_renew.is_(True),
        StudentSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED]),
        StudentSubscription.ends_on.is_not(None),
        StudentSubscription.ends_on <= horizon,
    ).order_by(StudentSubscription.ends_on, StudentSubscription.created_at)))

    for original in candidates:
        current = original
        while (
            current.auto_renew
            and current.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.EXPIRED}
            and current.ends_on is not None
            and current.ends_on <= horizon
        ):
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
            # An inactive tariff remains valid for the already-paid/current
            # period, but it must not be sold again automatically.
            if not plan.is_active:
                break

            current_period_days = current.period_days or plan.period_days or 30
            if current.ends_on < today - timedelta(days=current_period_days):
                skipped_stale_subscriptions += 1
                break

            next_start = _first_planned_lesson_date(
                db,
                org_id,
                current.group_id,
                current.ends_on + timedelta(days=1),
            )
            available_credit = max(0, current.credit_minor)
            applied_credit = min(available_credit, plan.price_minor)
            carry_credit = max(0, available_credit - applied_credit)
            amount_due = max(0, plan.price_minor - applied_credit)

            next_subscription = StudentSubscription(
                organization_id=org_id,
                student_id=student.id,
                plan_id=plan.id,
                group_id=current.group_id,
                status=SubscriptionStatus.ACTIVE,
                starts_on=next_start,
                ends_on=_subscription_end_date(next_start, plan.period_days),
                price_minor=plan.price_minor,
                period_days=plan.period_days,
                lessons_included=plan.lessons_included,
                lesson_unit_price_minor=_lesson_unit_price(plan.price_minor, plan.lessons_included),
                credit_minor=carry_credit,
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
                amount_minor=amount_due,
                currency=organization.currency,
                due_date=next_start,
                note=f"{plan.name} · автоматичне продовження",
                status=PaymentStatus.PAID if amount_due == 0 else PaymentStatus.PENDING,
                paid_at=datetime.now(timezone.utc) if amount_due == 0 else None,
            )
            db.add(payment)
            db.flush()
            current.credit_minor = 0
            if current.ends_on < today:
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
                    "tariff_price_minor": plan.price_minor,
                    "credit_applied_minor": applied_credit,
                    "amount_due_minor": amount_due,
                    "credit_carried_minor": carry_credit,
                },
                actor_user_id=actor_user_id,
            )
            created_payment_ids.append(payment.id)
            created_subscriptions += 1
            current = next_subscription

    if created_subscriptions or expired_rows:
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
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="Неактивний тариф не можна призначити новому абонементу")
    if data.discount_minor > plan.price_minor:
        raise HTTPException(status_code=422, detail="Знижка не може бути більшою за вартість тарифу")

    amount_minor = plan.price_minor - data.discount_minor
    if amount_minor <= 0:
        raise HTTPException(status_code=422, detail="Сума нарахування має бути більшою за нуль")

    group_id = getattr(data, "group_id", None)
    starts_on = _first_planned_lesson_date(db, org_id, group_id, data.starts_on)

    duplicate_subscription = db.scalar(select(StudentSubscription).where(
        StudentSubscription.organization_id == org_id,
        StudentSubscription.student_id == student.id,
        StudentSubscription.plan_id == plan.id,
        StudentSubscription.starts_on == starts_on,
        StudentSubscription.status != SubscriptionStatus.CANCELLED,
    ))
    if duplicate_subscription is not None:
        raise HTTPException(status_code=409, detail="На цей період уже є абонемент")

    subscription = StudentSubscription(
        organization_id=org_id,
        student_id=student.id,
        plan_id=plan.id,
        group_id=group_id,
        starts_on=starts_on,
        ends_on=_subscription_end_date(starts_on, plan.period_days),
        price_minor=plan.price_minor,
        period_days=plan.period_days,
        lessons_included=plan.lessons_included,
        lesson_unit_price_minor=_lesson_unit_price(amount_minor, plan.lessons_included),
        credit_minor=0,
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
        due_date=data.due_date or starts_on,
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
            "starts_on": starts_on.isoformat(),
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

def change_subscription_plan_now(
    db: Session,
    org_id: UUID,
    subscription_id: UUID,
    new_plan_id: UUID,
    reason: str,
    actor_user_id: UUID | None = None,
) -> dict:
    subscription = scoped_get(db, StudentSubscription, org_id, subscription_id)
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise HTTPException(status_code=409, detail="Скасований абонемент не можна змінити")
    old_plan = scoped_get(db, SubscriptionPlan, org_id, subscription.plan_id)
    new_plan = scoped_get(db, SubscriptionPlan, org_id, new_plan_id)
    if not new_plan.is_active:
        raise HTTPException(status_code=409, detail="Оберіть активний тариф")
    if old_plan.id == new_plan.id:
        raise HTTPException(status_code=409, detail="Цей тариф уже призначений учню")

    payment = db.scalar(select(Payment).where(
        Payment.organization_id == org_id,
        Payment.subscription_id == subscription.id,
        Payment.status != PaymentStatus.CANCELLED,
    ).order_by(Payment.created_at.desc()))
    if payment is None:
        raise HTTPException(status_code=409, detail="Для цього абонемента немає нарахування, яке можна перерахувати")

    _materialize_legacy_settlement(db, org_id, payment)
    finance_before = payment_financials(db, org_id, payment)
    summary = subscription_usage_summary(db, org_id, subscription)
    used_lessons = summary["used_lessons"]
    current_lessons = subscription.lessons_included
    if current_lessons is None and subscription.period_days is None:
        current_lessons = old_plan.lessons_included

    old_unit = subscription.lesson_unit_price_minor
    if old_unit is None and current_lessons:
        old_unit = _lesson_unit_price(finance_before["adjusted_amount_minor"], current_lessons)

    if used_lessons > 0:
        if current_lessons is None or new_plan.lessons_included is None:
            raise HTTPException(
                status_code=409,
                detail="Після початку періоду тариф можна змінити одразу лише коли обидва тарифи мають кількість занять.",
            )
        if new_plan.lessons_included != current_lessons:
            raise HTTPException(
                status_code=409,
                detail="Посеред періоду кількість занять не змінюємо. Нову кількість застосуйте з наступного періоду.",
            )
        remaining_lessons = max(0, current_lessons - used_lessons)
        old_unit = old_unit or 0
        new_unit = _lesson_unit_price(new_plan.price_minor, new_plan.lessons_included) or 0
        current_future_value = old_unit * remaining_lessons
        new_future_value = new_unit * remaining_lessons
        current_period_charge = max(
            0,
            finance_before["adjusted_amount_minor"] - current_future_value + new_future_value,
        )
    else:
        remaining_lessons = new_plan.lessons_included
        new_unit = _lesson_unit_price(new_plan.price_minor, new_plan.lessons_included)
        current_period_charge = new_plan.price_minor
        subscription.period_days = new_plan.period_days
        subscription.lessons_included = new_plan.lessons_included
        subscription.ends_on = _subscription_end_date(subscription.starts_on, new_plan.period_days)

    difference = current_period_charge - finance_before["adjusted_amount_minor"]
    if difference:
        db.add(PaymentTransaction(
            organization_id=org_id,
            payment_id=payment.id,
            student_id=payment.student_id,
            kind="adjustment_increase" if difference > 0 else "adjustment_decrease",
            amount_minor=abs(difference),
            note=f"Зміна тарифу зараз: {reason}",
            actor_user_id=actor_user_id,
        ))
        db.flush()

    subscription.plan_id = new_plan.id
    subscription.price_minor = current_period_charge
    subscription.lesson_unit_price_minor = new_unit
    subscription.discount_minor = 0
    subscription.discount_label = None

    finance_after = _sync_payment_state(db, org_id, payment)
    subscription.credit_minor = finance_after["credit_minor"]
    if payment.status != PaymentStatus.PAID:
        payment.paid_at = None

    record_audit(
        db,
        org_id,
        "student",
        subscription.student_id,
        "subscription.plan_changed_now",
        {
            "subscription_id": str(subscription.id),
            "payment_id": str(payment.id),
            "old_plan_id": str(old_plan.id),
            "old_plan_name": old_plan.name,
            "new_plan_id": str(new_plan.id),
            "new_plan_name": new_plan.name,
            "used_lessons": used_lessons,
            "remaining_lessons": remaining_lessons,
            "old_unit_price_minor": old_unit,
            "new_unit_price_minor": new_unit,
            "previous_charge_minor": finance_before["adjusted_amount_minor"],
            "current_period_charge_minor": current_period_charge,
            "credit_minor": finance_after["credit_minor"],
            "debt_minor": finance_after["balance_minor"],
            "reason": reason,
        },
        actor_user_id=actor_user_id,
    )
    db.commit()
    db.refresh(subscription)
    db.refresh(payment)
    payment.plan_id = new_plan.id
    _attach_subscription_usage(db, org_id, subscription)
    _attach_payment_financials(db, org_id, payment)
    return {
        "subscription": subscription,
        "payment": payment,
        "used_lessons": used_lessons,
        "old_plan_id": old_plan.id,
        "new_plan_id": new_plan.id,
        "old_unit_price_minor": old_unit,
        "new_unit_price_minor": new_unit,
        "current_period_charge_minor": current_period_charge,
        "credit_minor": payment.credit_minor,
        "debt_minor": payment.balance_minor,
    }


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
        can_teach=data.can_teach or data.role == StaffRole.TEACHER,
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
    next_role = payload.get("role", item.role)
    next_can_teach = payload.get("can_teach", item.can_teach)
    if next_role == StaffRole.TEACHER:
        next_can_teach = True
        payload["can_teach"] = True
    if item.can_teach and not next_can_teach:
        assigned_group = db.scalar(select(GroupStaff.id).where(
            GroupStaff.organization_id == org_id,
            GroupStaff.staff_id == staff_id,
        ).limit(1))
        if assigned_group is not None:
            raise HTTPException(status_code=409, detail="Remove this staff member from teaching groups before disabling teaching")
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
    scoped_get(db, Group, org_id, group_id)
    if not staff.is_active:
        raise HTTPException(status_code=409, detail="Inactive staff member cannot be assigned")
    if not staff.can_teach:
        raise HTTPException(status_code=409, detail="Staff member is not marked as able to teach")

    existing = db.scalar(select(GroupStaff).where(
        GroupStaff.organization_id == org_id,
        GroupStaff.staff_id == staff_id,
        GroupStaff.group_id == group_id,
    ))

    if is_primary:
        primary_rows = list(db.scalars(select(GroupStaff).where(
            GroupStaff.organization_id == org_id,
            GroupStaff.group_id == group_id,
            GroupStaff.is_primary.is_(True),
        )))
        for row in primary_rows:
            if row.staff_id != staff_id:
                row.is_primary = False

    if existing:
        existing.is_primary = is_primary
        db.commit()
        db.refresh(existing)
        return existing

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
            "student_phone": student.phone,
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
            "deferred_until": student.deferred_until,
            "deferred_reason": student.deferred_reason,
            "deferred_note": student.deferred_note,
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
            "student_phone": student.phone,
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
        primary_assignment = db.execute(
            select(GroupStaff, Staff)
            .join(Staff, Staff.id == GroupStaff.staff_id)
            .where(
                GroupStaff.organization_id == org_id,
                GroupStaff.group_id == group.id,
                Staff.organization_id == org_id,
                Staff.is_active.is_(True),
            )
            .order_by(GroupStaff.is_primary.desc(), Staff.full_name)
            .limit(1)
        ).first()
        primary_staff = primary_assignment[1] if primary_assignment else None
        result.append({
            "group_id": group.id,
            "name": group.name,
            "location_id": group.location_id,
            "location_name": location.name if location else None,
            "capacity": group.capacity,
            "enrolled_count": int(enrolled_count),
            "min_age": group.min_age,
            "max_age": group.max_age,
            "primary_teacher_id": primary_staff.id if primary_staff else None,
            "primary_teacher_name": primary_staff.full_name if primary_staff else None,
        })
    return result


def assigned_group_ids_for_user(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole) -> set[UUID] | None:
    if role in {StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER}:
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
