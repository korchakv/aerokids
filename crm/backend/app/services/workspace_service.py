from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.core import (
    Contact,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupStaff,
    Location,
    Staff,
    StaffRole,
    Student,
    StudentContact,
    StudentStatus,
    TrialLesson,
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



def _lead_overview_item(db: Session, org_id: UUID, student: Student) -> dict:
    contact = _primary_contact_for_student(db, org_id, student.id)
    trial = db.scalar(
        select(TrialLesson)
        .where(TrialLesson.organization_id == org_id, TrialLesson.student_id == student.id)
        .order_by(TrialLesson.starts_at.desc())
        .limit(1)
    )
    trial_location = scoped_get(db, Location, org_id, trial.location_id) if trial and trial.location_id else None
    preferences = student_preferences(db, org_id, student.id)
    return {
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
    }


def _active_group_for_student(db: Session, org_id: UUID, student_id: UUID) -> Group | None:
    row = db.execute(
        select(Group)
        .join(Enrollment, Enrollment.group_id == Group.id)
        .where(
            Enrollment.organization_id == org_id,
            Enrollment.student_id == student_id,
            Enrollment.status == EnrollmentStatus.ACTIVE,
            Group.organization_id == org_id,
        )
        .order_by(Enrollment.started_at.desc(), Enrollment.id.desc())
        .limit(1)
    ).first()
    return row[0] if row else None


def _student_overview_item(db: Session, org_id: UUID, student: Student) -> dict:
    contact = _primary_contact_for_student(db, org_id, student.id)
    group = _active_group_for_student(db, org_id, student.id)
    return {
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
    }


def _group_overview_item(db: Session, org_id: UUID, group: Group) -> dict:
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
    return {
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
    }


def _page_result(items: list[dict], total: int, limit: int, offset: int) -> dict:
    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(items) < total,
    }


def paginate_lead_overview(
    db: Session,
    org_id: UUID,
    q: str | None,
    limit: int,
    offset: int,
    sort: str = "created_at",
    order: str = "desc",
) -> dict:
    stmt = select(Student).where(
        Student.organization_id == org_id,
        Student.student_status == StudentStatus.PROSPECT,
    )
    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        contact_match = select(StudentContact.student_id).join(
            Contact, Contact.id == StudentContact.contact_id
        ).where(
            StudentContact.organization_id == org_id,
            Contact.organization_id == org_id,
            or_(Contact.full_name.ilike(pattern), Contact.phone.ilike(pattern)),
        )
        stmt = stmt.where(or_(
            Student.first_name.ilike(pattern),
            Student.last_name.ilike(pattern),
            Student.phone.ilike(pattern),
            Student.source.ilike(pattern),
            Student.id.in_(contact_match),
        ))
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    sort_expr = Student.created_at if sort == "created_at" else Student.first_name
    sort_expr = sort_expr.desc() if order == "desc" else sort_expr.asc()
    students = list(db.scalars(
        stmt.order_by(sort_expr, Student.id.asc()).offset(offset).limit(limit)
    ))
    return _page_result([_lead_overview_item(db, org_id, student) for student in students], total, limit, offset)


def paginate_student_overview(
    db: Session,
    org_id: UUID,
    user_id: UUID | None,
    role: StaffRole,
    q: str | None,
    limit: int,
    offset: int,
    sort: str = "name",
    order: str = "asc",
) -> dict:
    stmt = select(Student).where(
        Student.organization_id == org_id,
        Student.student_status != StudentStatus.PROSPECT,
    )
    allowed_groups = None if role == StaffRole.ACCOUNTANT else assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed_groups is not None:
        if not allowed_groups:
            return _page_result([], 0, limit, offset)
        scoped_students = select(Enrollment.student_id).where(
            Enrollment.organization_id == org_id,
            Enrollment.group_id.in_(allowed_groups),
            Enrollment.status == EnrollmentStatus.ACTIVE,
        )
        stmt = stmt.where(Student.id.in_(scoped_students))

    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        contact_match = select(StudentContact.student_id).join(
            Contact, Contact.id == StudentContact.contact_id
        ).where(
            StudentContact.organization_id == org_id,
            Contact.organization_id == org_id,
            or_(Contact.full_name.ilike(pattern), Contact.phone.ilike(pattern)),
        )
        stmt = stmt.where(or_(
            Student.first_name.ilike(pattern),
            Student.last_name.ilike(pattern),
            Student.phone.ilike(pattern),
            Student.source.ilike(pattern),
            Student.id.in_(contact_match),
        ))

    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    if sort == "status":
        sort_expr = Student.student_status
        tie_breaker = Student.first_name
    else:
        sort_expr = Student.first_name
        tie_breaker = Student.last_name
    sort_expr = sort_expr.desc() if order == "desc" else sort_expr.asc()
    students = list(db.scalars(
        stmt.order_by(sort_expr, tie_breaker.asc(), Student.id.asc()).offset(offset).limit(limit)
    ))
    return _page_result([_student_overview_item(db, org_id, student) for student in students], total, limit, offset)


def paginate_group_overview(
    db: Session,
    org_id: UUID,
    user_id: UUID | None,
    role: StaffRole,
    q: str | None,
    limit: int,
    offset: int,
    sort: str = "name",
    order: str = "asc",
) -> dict:
    stmt = select(Group).where(
        Group.organization_id == org_id,
        Group.is_active.is_(True),
    )
    allowed_groups = assigned_group_ids_for_user(db, org_id, user_id, role)
    if allowed_groups is not None:
        if not allowed_groups:
            return _page_result([], 0, limit, offset)
        stmt = stmt.where(Group.id.in_(allowed_groups))

    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        location_match = select(Location.id).where(
            Location.organization_id == org_id,
            Location.name.ilike(pattern),
        )
        teacher_group_match = select(GroupStaff.group_id).join(
            Staff, Staff.id == GroupStaff.staff_id
        ).where(
            GroupStaff.organization_id == org_id,
            Staff.organization_id == org_id,
            Staff.is_active.is_(True),
            Staff.full_name.ilike(pattern),
        )
        stmt = stmt.where(or_(
            Group.name.ilike(pattern),
            Group.location_id.in_(location_match),
            Group.id.in_(teacher_group_match),
        ))

    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    sort_expr = Group.name
    if sort == "capacity":
        sort_expr = Group.capacity
    sort_expr = sort_expr.desc() if order == "desc" else sort_expr.asc()
    groups = list(db.scalars(
        stmt.order_by(sort_expr, Group.name.asc(), Group.id.asc()).offset(offset).limit(limit)
    ))
    return _page_result([_group_overview_item(db, org_id, group) for group in groups], total, limit, offset)



def list_lead_overview(db: Session, org_id: UUID) -> list[dict]:
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.student_status == StudentStatus.PROSPECT)
        .order_by(Student.created_at.desc())
    ))
    return [_lead_overview_item(db, org_id, student) for student in students]

def list_student_overview(db: Session, org_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    allowed_groups = None if role == StaffRole.ACCOUNTANT else assigned_group_ids_for_user(db, org_id, user_id, role)
    students = list(db.scalars(
        select(Student)
        .where(Student.organization_id == org_id, Student.student_status != StudentStatus.PROSPECT)
        .order_by(Student.first_name, Student.last_name)
    ))
    result = []
    for student in students:
        item = _student_overview_item(db, org_id, student)
        if allowed_groups is not None and item["group_id"] not in allowed_groups:
            continue
        result.append(item)
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
    return [_group_overview_item(db, org_id, group) for group in groups]

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

