from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.core import (
    Contact,
    CrmStatus,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupStaff,
    Location,
    Staff,
    StaffRole,
    Student,
    StudentAvailability,
    StudentContact,
    StudentStatus,
    TrialLesson,
    TrialStatus,
)
from app.services import crm

# Lazy-loaded by the legacy crm facade after crm.py has initialized.
scoped_get = crm.scoped_get
student_preferences = crm.student_preferences

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



LEAD_COLUMNS = {"new", "contacted", "trial", "no_show", "after_trial", "waiting", "deferred", "closed"}


def _lead_projection_subqueries(org_id: UUID):
    contact_name = (
        select(Contact.full_name)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == Student.id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.created_at)
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )
    contact_phone = (
        select(Contact.phone)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == Student.id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.created_at)
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )
    preferred_location_name = (
        select(Location.name)
        .where(Location.organization_id == org_id, Location.id == Student.preferred_location_id)
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )

    def trial_field(column):
        return (
            select(column)
            .where(
                TrialLesson.organization_id == org_id,
                TrialLesson.student_id == Student.id,
            )
            .order_by(TrialLesson.starts_at.desc(), TrialLesson.id.desc())
            .limit(1)
            .correlate(Student)
            .scalar_subquery()
        )

    latest_trial_id = trial_field(TrialLesson.id)
    latest_trial_at = trial_field(TrialLesson.starts_at)
    latest_trial_status = trial_field(TrialLesson.status)
    latest_trial_location_id = trial_field(TrialLesson.location_id)
    latest_trial_level = trial_field(TrialLesson.recommended_level)
    latest_trial_notes = trial_field(TrialLesson.teacher_notes)
    trial_location_name = (
        select(Location.name)
        .where(Location.organization_id == org_id, Location.id == latest_trial_location_id)
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )
    return {
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "preferred_location_name": preferred_location_name,
        "latest_trial_id": latest_trial_id,
        "latest_trial_at": latest_trial_at,
        "latest_trial_status": latest_trial_status,
        "latest_trial_location_id": latest_trial_location_id,
        "latest_trial_level": latest_trial_level,
        "latest_trial_notes": latest_trial_notes,
        "trial_location_name": trial_location_name,
    }


def _lead_column_condition(column: str, latest_trial_status, now: datetime):
    closed_statuses = (CrmStatus.DECLINED, CrmStatus.NO_RESPONSE, CrmStatus.NOT_RELEVANT)
    closed = Student.crm_status.in_(closed_statuses)
    deferred = and_(
        ~closed,
        Student.deferred_until.is_not(None),
        Student.deferred_until > now,
    )
    active_now = or_(Student.deferred_until.is_(None), Student.deferred_until <= now)
    if column == "closed":
        return closed
    if column == "deferred":
        return deferred
    if column == "no_show":
        return and_(~closed, active_now, Student.crm_status == CrmStatus.CONTACTED, latest_trial_status == TrialStatus.NO_SHOW)
    if column == "after_trial":
        return and_(~closed, active_now, Student.crm_status == CrmStatus.TRIAL_COMPLETED)
    if column == "trial":
        return and_(~closed, active_now, Student.crm_status == CrmStatus.TRIAL_SCHEDULED)
    if column == "waiting":
        return and_(~closed, active_now, Student.crm_status == CrmStatus.WAITING_FOR_GROUP)
    if column == "new":
        return and_(~closed, active_now, Student.crm_status == CrmStatus.NEW)
    if column == "contacted":
        return and_(
            ~closed,
            active_now,
            Student.crm_status == CrmStatus.CONTACTED,
            or_(latest_trial_status.is_(None), latest_trial_status != TrialStatus.NO_SHOW),
        )
    raise HTTPException(status_code=422, detail="Unsupported lead column")


def paginate_lead_overview(
    db: Session,
    org_id: UUID,
    *,
    q: str | None = None,
    column: str | None = None,
    source: str | None = None,
    sort: str = "priority",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Database-backed lead page with batched availability and no ORM N+1 loop."""
    projection = _lead_projection_subqueries(org_id)
    now = datetime.now(timezone.utc)
    filters = [
        Student.organization_id == org_id,
        Student.student_status == StudentStatus.PROSPECT,
    ]
    if column is not None:
        if column not in LEAD_COLUMNS:
            raise HTTPException(status_code=422, detail="Unsupported lead column")
        filters.append(_lead_column_condition(column, projection["latest_trial_status"], now))
    if source:
        filters.append(Student.source == source)

    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        contact_match = exists(
            select(StudentContact.id)
            .join(Contact, Contact.id == StudentContact.contact_id)
            .where(
                StudentContact.organization_id == org_id,
                StudentContact.student_id == Student.id,
                Contact.organization_id == org_id,
                or_(Contact.full_name.ilike(pattern), Contact.phone.ilike(pattern)),
            )
        )
        filters.append(or_(
            Student.first_name.ilike(pattern),
            Student.last_name.ilike(pattern),
            Student.phone.ilike(pattern),
            contact_match,
        ))

    total = int(db.scalar(select(func.count(Student.id)).where(*filters)) or 0)
    statement = select(
        Student,
        projection["contact_name"].label("contact_name"),
        projection["contact_phone"].label("contact_phone"),
        projection["preferred_location_name"].label("preferred_location_name"),
        projection["latest_trial_id"].label("latest_trial_id"),
        projection["latest_trial_at"].label("latest_trial_at"),
        projection["latest_trial_status"].label("latest_trial_status"),
        projection["latest_trial_location_id"].label("trial_location_id"),
        projection["trial_location_name"].label("trial_location_name"),
        projection["latest_trial_level"].label("recommended_level"),
        projection["latest_trial_notes"].label("teacher_notes"),
    ).where(*filters)

    next_action = func.coalesce(Student.next_contact_at, projection["latest_trial_at"])
    priority = case(
        (and_(Student.next_contact_at.is_not(None), Student.next_contact_at <= now), 0),
        (projection["latest_trial_status"] == TrialStatus.NO_SHOW, 1),
        (projection["latest_trial_status"] == TrialStatus.CANCELLED, 2),
        (and_(Student.crm_status == CrmStatus.TRIAL_COMPLETED, Student.next_contact_at.is_(None)), 3),
        (Student.crm_status == CrmStatus.NEW, 4),
        (Student.crm_status == CrmStatus.TRIAL_SCHEDULED, 5),
        (Student.next_contact_at.is_not(None), 6),
        (Student.crm_status == CrmStatus.CONTACTED, 7),
        (Student.crm_status == CrmStatus.WAITING_FOR_GROUP, 8),
        else_=9,
    )
    if sort == "newest":
        statement = statement.order_by(Student.created_at.desc(), Student.id)
    elif sort == "next_action":
        statement = statement.order_by(next_action.is_(None), next_action, priority, Student.created_at.desc(), Student.id)
    else:
        statement = statement.order_by(priority, next_action.is_(None), next_action, Student.created_at.desc(), Student.id)

    rows = db.execute(statement.offset(offset).limit(limit)).all()
    student_ids = [row[0].id for row in rows]
    availability_by_student: dict[UUID, list[dict]] = {student_id: [] for student_id in student_ids}
    if student_ids:
        availability_rows = db.scalars(
            select(StudentAvailability)
            .where(
                StudentAvailability.organization_id == org_id,
                StudentAvailability.student_id.in_(student_ids),
            )
            .order_by(StudentAvailability.student_id, StudentAvailability.weekday, StudentAvailability.start_time)
        )
        for slot in availability_rows:
            availability_by_student.setdefault(slot.student_id, []).append({
                "weekday": slot.weekday,
                "start_time": slot.start_time,
                "end_time": slot.end_time,
                "preference": slot.preference,
                "note": slot.note,
            })

    items = []
    for row in rows:
        student = row[0]
        items.append({
            "student_id": student.id,
            "created_at": student.created_at,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "student_phone": student.phone,
            "age": student.age_at_inquiry,
            "source": student.source,
            "comment": student.notes,
            "preferred_location_id": student.preferred_location_id,
            "preferred_location_name": row.preferred_location_name,
            "availability": availability_by_student.get(student.id, []),
            "crm_status": student.crm_status,
            "contact_name": row.contact_name,
            "contact_phone": row.contact_phone,
            "latest_trial_id": row.latest_trial_id,
            "latest_trial_at": row.latest_trial_at,
            "latest_trial_status": row.latest_trial_status,
            "trial_location_id": row.trial_location_id,
            "trial_location_name": row.trial_location_name,
            "recommended_level": row.recommended_level,
            "teacher_notes": row.teacher_notes,
            "next_contact_at": student.next_contact_at,
            "deferred_until": student.deferred_until,
            "deferred_reason": student.deferred_reason,
            "deferred_note": student.deferred_note,
            "close_reason": student.lead_close_reason,
            "close_note": student.lead_close_note,
        })
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def lead_column_counts(db: Session, org_id: UUID) -> dict[str, int]:
    projection = _lead_projection_subqueries(org_id)
    now = datetime.now(timezone.utc)
    base = [
        Student.organization_id == org_id,
        Student.student_status == StudentStatus.PROSPECT,
    ]
    result: dict[str, int] = {}
    for column in LEAD_COLUMNS:
        result[column] = int(db.scalar(
            select(func.count(Student.id)).where(
                *base,
                _lead_column_condition(column, projection["latest_trial_status"], now),
            )
        ) or 0)
    return result


def paginate_student_overview(
    db: Session,
    org_id: UUID,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
    *,
    q: str | None = None,
    status: StudentStatus | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Database-backed page for the student registry.

    Unlike the legacy overview helper, filtering, counting and pagination happen
    before rows are materialized. The returned item shape intentionally matches
    the existing workspace student contract.
    """
    # Preserve the legacy finance workflow: accountants can resolve students
    # across the organization for billing, while teachers remain assigned-group scoped.
    allowed_groups = None if role == StaffRole.ACCOUNTANT else assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed_groups is not None and not allowed_groups:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    contact_name = (
        select(Contact.full_name)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == Student.id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.created_at)
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )
    contact_phone = (
        select(Contact.phone)
        .join(StudentContact, StudentContact.contact_id == Contact.id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id == Student.id,
            Contact.organization_id == org_id,
        )
        .order_by(StudentContact.is_primary.desc(), Contact.created_at)
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )
    group_projection_filters = [
        Enrollment.organization_id == org_id,
        Enrollment.student_id == Student.id,
        Enrollment.status == EnrollmentStatus.ACTIVE,
        Group.organization_id == org_id,
        Group.is_active.is_(True),
    ]
    if allowed_groups is not None:
        group_projection_filters.append(Group.id.in_(allowed_groups))

    current_group_id = (
        select(Group.id)
        .join(Enrollment, Enrollment.group_id == Group.id)
        .where(*group_projection_filters)
        .order_by(Enrollment.started_at.desc(), Enrollment.id.desc())
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )
    current_group_name = (
        select(Group.name)
        .join(Enrollment, Enrollment.group_id == Group.id)
        .where(*group_projection_filters)
        .order_by(Enrollment.started_at.desc(), Enrollment.id.desc())
        .limit(1)
        .correlate(Student)
        .scalar_subquery()
    )

    filters = [
        Student.organization_id == org_id,
        Student.student_status != StudentStatus.PROSPECT,
    ]
    if status is not None:
        filters.append(Student.student_status == status)

    if allowed_groups is not None:
        filters.append(exists(
            select(Enrollment.id).where(
                Enrollment.organization_id == org_id,
                Enrollment.student_id == Student.id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
                Enrollment.group_id.in_(allowed_groups),
            )
        ))

    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        contact_match = exists(
            select(StudentContact.id)
            .join(Contact, Contact.id == StudentContact.contact_id)
            .where(
                StudentContact.organization_id == org_id,
                StudentContact.student_id == Student.id,
                Contact.organization_id == org_id,
                or_(Contact.full_name.ilike(pattern), Contact.phone.ilike(pattern)),
            )
        )
        filters.append(or_(
            Student.first_name.ilike(pattern),
            Student.last_name.ilike(pattern),
            Student.phone.ilike(pattern),
            contact_match,
        ))

    total = int(db.scalar(select(func.count(Student.id)).where(*filters)) or 0)
    statement = select(
        Student,
        contact_name.label("contact_name"),
        contact_phone.label("contact_phone"),
        current_group_id.label("group_id"),
        current_group_name.label("group_name"),
    ).where(*filters)

    if sort == "newest":
        statement = statement.order_by(Student.created_at.desc(), Student.id)
    elif sort == "oldest":
        statement = statement.order_by(Student.created_at, Student.id)
    else:
        statement = statement.order_by(Student.first_name, Student.last_name, Student.id)

    rows = db.execute(statement.offset(offset).limit(limit)).all()
    items = [{
        "student_id": student.id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "student_phone": student.phone,
        "age": student.age_at_inquiry,
        "source": student.source,
        "student_status": student.student_status,
        "contact_name": row.contact_name,
        "contact_phone": row.contact_phone,
        "group_id": row.group_id,
        "group_name": row.group_name,
    } for row in rows for student in [row[0]]]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def paginate_group_overview(
    db: Session,
    org_id: UUID,
    user_id: UUID | None = None,
    role: StaffRole = StaffRole.OWNER,
    *,
    q: str | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Database-backed active-group page with aggregate projections."""
    location_name = (
        select(Location.name)
        .where(Location.organization_id == org_id, Location.id == Group.location_id)
        .limit(1)
        .correlate(Group)
        .scalar_subquery()
    )
    enrolled_count = (
        select(func.count(Enrollment.id))
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id == Group.id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
        .correlate(Group)
        .scalar_subquery()
    )
    primary_teacher_id = (
        select(Staff.id)
        .join(GroupStaff, GroupStaff.staff_id == Staff.id)
        .where(
            GroupStaff.organization_id == org_id,
            GroupStaff.group_id == Group.id,
            Staff.organization_id == org_id,
            Staff.is_active.is_(True),
        )
        .order_by(GroupStaff.is_primary.desc(), Staff.full_name, Staff.id)
        .limit(1)
        .correlate(Group)
        .scalar_subquery()
    )
    primary_teacher_name = (
        select(Staff.full_name)
        .join(GroupStaff, GroupStaff.staff_id == Staff.id)
        .where(
            GroupStaff.organization_id == org_id,
            GroupStaff.group_id == Group.id,
            Staff.organization_id == org_id,
            Staff.is_active.is_(True),
        )
        .order_by(GroupStaff.is_primary.desc(), Staff.full_name, Staff.id)
        .limit(1)
        .correlate(Group)
        .scalar_subquery()
    )

    filters = [Group.organization_id == org_id, Group.is_active.is_(True)]
    allowed_groups = assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed_groups is not None:
        if not allowed_groups:
            return {"items": [], "total": 0, "limit": limit, "offset": offset}
        filters.append(Group.id.in_(allowed_groups))

    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        location_match = exists(select(Location.id).where(
            Location.organization_id == org_id,
            Location.id == Group.location_id,
            Location.name.ilike(pattern),
        ))
        teacher_match = exists(
            select(GroupStaff.id)
            .join(Staff, Staff.id == GroupStaff.staff_id)
            .where(
                GroupStaff.organization_id == org_id,
                GroupStaff.group_id == Group.id,
                Staff.organization_id == org_id,
                Staff.is_active.is_(True),
                Staff.full_name.ilike(pattern),
            )
        )
        filters.append(or_(Group.name.ilike(pattern), location_match, teacher_match))

    total = int(db.scalar(select(func.count(Group.id)).where(*filters)) or 0)
    statement = select(
        Group,
        location_name.label("location_name"),
        enrolled_count.label("enrolled_count"),
        primary_teacher_id.label("primary_teacher_id"),
        primary_teacher_name.label("primary_teacher_name"),
    ).where(*filters)
    if sort == "size_desc":
        statement = statement.order_by(enrolled_count.desc(), Group.name, Group.id)
    elif sort == "size_asc":
        statement = statement.order_by(enrolled_count, Group.name, Group.id)
    else:
        statement = statement.order_by(Group.name, Group.id)

    rows = db.execute(statement.offset(offset).limit(limit)).all()
    items = [{
        "group_id": group.id,
        "name": group.name,
        "location_id": group.location_id,
        "location_name": row.location_name,
        "capacity": group.capacity,
        "enrolled_count": int(row.enrolled_count or 0),
        "min_age": group.min_age,
        "max_age": group.max_age,
        "primary_teacher_id": row.primary_teacher_id,
        "primary_teacher_name": row.primary_teacher_name,
    } for row in rows for group in [row[0]]]
    return {"items": items, "total": total, "limit": limit, "offset": offset}



def ensure_group_access(db: Session, org_id: UUID, user_id: UUID | None, role: StaffRole, group_id: UUID) -> Group:
    group = scoped_get(db, Group, org_id, group_id)
    allowed = assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed is not None and group_id not in allowed:
        raise HTTPException(status_code=403, detail="No access to this group")
    return group

