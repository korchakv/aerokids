"""Core group CRUD domain service extracted from the legacy CRM facade."""

from __future__ import annotations

from datetime import date, time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.core import (
    Attendance,
    AttendanceStatus,
    Contact,
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
    PaymentTransaction,
    StaffRole,
    Student,
    StudentContact,
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
    """Return one group detail using a bounded number of SQL queries.

    The previous implementation loaded student/contact/attendance/billing data
    inside the enrollment loop, which made query count grow with every member
    and every payment. This projection batches each domain once and preserves
    the existing API response shape.
    """
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
    if not enrollments:
        return {"group": group, "schedules": schedules, "members": []}

    student_ids = [item.student_id for item in enrollments]
    students = {
        item.id: item
        for item in db.scalars(
            select(Student).where(
                Student.organization_id == org_id,
                Student.id.in_(student_ids),
            )
        )
    }

    primary_contacts: dict[UUID, Contact] = {}
    contact_rows = db.execute(
        select(StudentContact.student_id, Contact)
        .join(Contact, Contact.id == StudentContact.contact_id)
        .where(
            StudentContact.organization_id == org_id,
            StudentContact.student_id.in_(student_ids),
            Contact.organization_id == org_id,
        )
        .order_by(
            StudentContact.student_id,
            StudentContact.is_primary.desc(),
            Contact.full_name,
            Contact.id,
        )
    ).all()
    for student_id, contact in contact_rows:
        primary_contacts.setdefault(student_id, contact)

    attendance_by_student: dict[UUID, dict[str, int]] = {
        student_id: {"present": 0, "absent": 0, "late": 0, "excused": 0}
        for student_id in student_ids
    }
    attendance_rows = db.execute(
        select(Attendance.student_id, Attendance.status, func.count(Attendance.id))
        .join(LessonSession, LessonSession.id == Attendance.session_id)
        .where(
            Attendance.organization_id == org_id,
            Attendance.student_id.in_(student_ids),
            LessonSession.organization_id == org_id,
            LessonSession.group_id == group.id,
        )
        .group_by(Attendance.student_id, Attendance.status)
    ).all()
    status_key = {
        AttendanceStatus.PRESENT: "present",
        AttendanceStatus.ABSENT: "absent",
        AttendanceStatus.LATE: "late",
        AttendanceStatus.EXCUSED: "excused",
    }
    for student_id, status, count in attendance_rows:
        key = status_key.get(status)
        if key is not None:
            attendance_by_student.setdefault(
                student_id,
                {"present": 0, "absent": 0, "late": 0, "excused": 0},
            )[key] = int(count)

    # Teachers receive academic data only. This is both a privacy rule and
    # avoids performing finance queries only to strip them later.
    finance_visible = role in {
        StaffRole.OWNER,
        StaffRole.ADMIN,
        StaffRole.MANAGER,
        StaffRole.ACCOUNTANT,
    }
    payments_by_student: dict[UUID, list[Payment]] = {student_id: [] for student_id in student_ids}
    subscriptions_by_student: dict[UUID, list[StudentSubscription]] = {student_id: [] for student_id in student_ids}
    plans_by_id: dict[UUID, SubscriptionPlan] = {}
    usage_by_subscription: dict[UUID, int] = {}

    if finance_visible:
        payment_rows = list(db.scalars(
            select(Payment)
            .where(
                Payment.organization_id == org_id,
                Payment.student_id.in_(student_ids),
            )
            .order_by(Payment.student_id, Payment.created_at.desc(), Payment.id.desc())
        ))
        for payment in payment_rows:
            payments_by_student.setdefault(payment.student_id, []).append(payment)

        payment_ids = [payment.id for payment in payment_rows]
        transactions_by_payment: dict[UUID, list[PaymentTransaction]] = {
            payment_id: [] for payment_id in payment_ids
        }
        if payment_ids:
            for transaction in db.scalars(
                select(PaymentTransaction)
                .where(
                    PaymentTransaction.organization_id == org_id,
                    PaymentTransaction.payment_id.in_(payment_ids),
                )
                .order_by(PaymentTransaction.payment_id, PaymentTransaction.occurred_at, PaymentTransaction.id)
            ):
                transactions_by_payment.setdefault(transaction.payment_id, []).append(transaction)

        for payment in payment_rows:
            transactions = transactions_by_payment.get(payment.id, [])
            increases = sum(item.amount_minor for item in transactions if item.kind == "adjustment_increase")
            decreases = sum(item.amount_minor for item in transactions if item.kind == "adjustment_decrease")
            adjusted_amount = max(0, payment.amount_minor + increases - decreases)
            paid_minor = sum(item.amount_minor for item in transactions if item.kind == "payment")
            refunded_minor = sum(item.amount_minor for item in transactions if item.kind == "refund")
            if not transactions and payment.status == PaymentStatus.PAID:
                paid_minor = adjusted_amount
            net_paid = max(0, paid_minor - refunded_minor)
            payment.adjusted_amount_minor = adjusted_amount
            payment.paid_minor = paid_minor
            payment.refunded_minor = refunded_minor
            payment.balance_minor = max(0, adjusted_amount - net_paid)
            payment.credit_minor = max(0, net_paid - adjusted_amount)

        subscriptions = list(db.scalars(
            select(StudentSubscription)
            .where(
                StudentSubscription.organization_id == org_id,
                StudentSubscription.student_id.in_(student_ids),
            )
            .order_by(
                StudentSubscription.student_id,
                StudentSubscription.starts_on.desc(),
                StudentSubscription.created_at.desc(),
                StudentSubscription.id.desc(),
            )
        ))
        subscription_by_id = {item.id: item for item in subscriptions}
        for subscription in subscriptions:
            subscriptions_by_student.setdefault(subscription.student_id, []).append(subscription)

        for payment in payment_rows:
            linked = subscription_by_id.get(payment.subscription_id) if payment.subscription_id else None
            payment.plan_id = linked.plan_id if linked else None

        plan_ids = {item.plan_id for item in subscriptions}
        if plan_ids:
            plans_by_id = {
                plan.id: plan
                for plan in db.scalars(
                    select(SubscriptionPlan).where(
                        SubscriptionPlan.organization_id == org_id,
                        SubscriptionPlan.id.in_(plan_ids),
                    )
                )
            }

        latest_subscription_ids = {
            items[0].id for items in subscriptions_by_student.values() if items
        }
        if latest_subscription_ids:
            usage_rows = db.execute(
                select(
                    SubscriptionUsage.subscription_id,
                    func.coalesce(func.sum(SubscriptionUsage.units), 0),
                )
                .where(
                    SubscriptionUsage.organization_id == org_id,
                    SubscriptionUsage.subscription_id.in_(latest_subscription_ids),
                )
                .group_by(SubscriptionUsage.subscription_id)
            ).all()
            usage_by_subscription = {
                subscription_id: int(units or 0)
                for subscription_id, units in usage_rows
            }

    today = date.today()
    members = []
    for enrollment in enrollments:
        student = students.get(enrollment.student_id)
        if student is None:
            # Tenant integrity audit should catch this, but a broken historical
            # reference must not crash the whole group detail response.
            continue
        contact = primary_contacts.get(student.id)

        attendance_counts = attendance_by_student.get(
            student.id,
            {"present": 0, "absent": 0, "late": 0, "excused": 0},
        )
        attendance_total = sum(attendance_counts.values())
        attended = attendance_counts["present"] + attendance_counts["late"]
        attendance_summary = {
            **attendance_counts,
            "total": attendance_total,
            "attendance_rate": round(attended / attendance_total * 100, 1) if attendance_total else 0.0,
        }

        payment_rows = payments_by_student.get(student.id, []) if finance_visible else []
        billing = None
        if finance_visible:
            subscriptions = subscriptions_by_student.get(student.id, [])
            latest_subscription = subscriptions[0] if subscriptions else None
            plan = plans_by_id.get(latest_subscription.plan_id) if latest_subscription else None
            lessons_used = None
            lessons_remaining = None
            if latest_subscription and plan:
                lessons_used = usage_by_subscription.get(latest_subscription.id, 0)
                included_for_usage = latest_subscription.lessons_included
                if included_for_usage is None and latest_subscription.period_days is None:
                    included_for_usage = plan.lessons_included
                lessons_remaining = (
                    max(0, included_for_usage - lessons_used)
                    if included_for_usage is not None
                    else None
                )

            pending = [
                item for item in payment_rows
                if item.status != PaymentStatus.CANCELLED and item.balance_minor > 0
            ]
            dated_pending = [item for item in pending if item.due_date is not None]
            overdue = [item for item in dated_pending if item.due_date < today]
            due_today = [item for item in dated_pending if item.due_date == today]
            next_due_date = min((item.due_date for item in dated_pending), default=None)
            last_paid = next(
                (item for item in payment_rows if item.paid_minor - item.refunded_minor > 0),
                None,
            )
            if overdue:
                billing_status = "overdue"
            elif due_today:
                billing_status = "due"
            elif pending:
                billing_status = "upcoming"
            elif (
                latest_subscription
                and latest_subscription.status == SubscriptionStatus.ACTIVE
                and (latest_subscription.ends_on is None or latest_subscription.ends_on >= today)
            ):
                billing_status = "current"
            else:
                billing_status = "no_plan"

            billing = {
                "status": billing_status,
                "plan_name": plan.name if plan else None,
                "lessons_used": lessons_used,
                "lessons_included": (
                    latest_subscription.lessons_included
                    if latest_subscription
                    else (plan.lessons_included if plan else None)
                ),
                "lessons_remaining": lessons_remaining,
                "amount_due_minor": sum(item.balance_minor for item in pending),
                "next_due_date": next_due_date,
                "last_paid_at": last_paid.paid_at if last_paid else None,
                "last_paid_minor": (
                    last_paid.paid_minor - last_paid.refunded_minor
                    if last_paid
                    else None
                ),
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

