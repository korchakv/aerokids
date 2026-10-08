"""Core group CRUD domain service extracted from the legacy CRM facade."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    AttendanceStatus,
    Enrollment,
    EnrollmentStatus,
    Group,
    GroupSchedule,
    GroupStaff,
    LessonSession,
    LessonStatus,
    Location,
    MakeupCredit,
    Organization,
    Payment,
    PaymentStatus,
    StaffRole,
    Student,
    StudentStatus,
    StudentSubscription,
    SubscriptionPlan,
    SubscriptionStatus,
    SubscriptionUsage,
)
from app.services import audit_service, billing_service, workspace_service


def _require_organization(db: Session, org_id: UUID) -> Organization:
    organization = db.get(Organization, org_id)
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    return organization


def _scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_group(db: Session, org_id: UUID, data) -> Group:
    _require_organization(db, org_id)
    if data.location_id:
        _scoped_get(db, Location, org_id, data.location_id)
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
    data,
    actor_user_id: UUID | None = None,
) -> Group:
    group = _scoped_get(db, Group, org_id, group_id)
    if data.location_id is not None:
        _scoped_get(db, Location, org_id, data.location_id)

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

    audit_service.record_audit(
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
    group = _scoped_get(db, Group, org_id, group_id)

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

    audit_service.record_audit(
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
    return list(
        db.scalars(
            select(Group)
            .where(Group.organization_id == org_id, Group.is_active.is_(True))
            .order_by(Group.name)
        )
    )


def group_roster(db: Session, org_id: UUID, group_id: UUID, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[dict]:
    workspace_service.ensure_group_access(db, org_id, user_id, role, group_id)
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
        group = _scoped_get(db, Group, org_id, group_id)
    else:
        group = workspace_service.ensure_group_access(db, org_id, user_id, role, group_id)

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
        student = _scoped_get(db, Student, org_id, enrollment.student_id)
        contact = workspace_service._primary_contact_for_student(db, org_id, student.id)

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
                billing_service._attach_payment_financials(db, org_id, payment)

            latest_subscription = subscriptions[0] if subscriptions else None
            plan = _scoped_get(db, SubscriptionPlan, org_id, latest_subscription.plan_id) if latest_subscription else None
            lessons_used = None
            lessons_remaining = None
            if latest_subscription and plan:
                usage_summary = billing_service.subscription_usage_summary(db, org_id, latest_subscription)
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


