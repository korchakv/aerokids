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
    from app.services import audit_service
    return audit_service.record_audit(
        db, org_id, entity_type, entity_id, event_type, payload, actor_user_id,
    )


def list_audit_events(
    db: Session,
    org_id: UUID,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = 100,
) -> list[dict]:
    from app.services import audit_service
    return audit_service.list_audit_events(db, org_id, entity_type, entity_id, limit)

def _enrollment_service_call(name: str, *args, **kwargs):
    from app.services import enrollment_service
    return getattr(enrollment_service, name)(*args, **kwargs)


def ensure_group_capacity(*args, **kwargs):
    return _enrollment_service_call("ensure_group_capacity", *args, **kwargs)


def _lead_service_call(name: str, *args, **kwargs):
    from app.services import lead_service
    return getattr(lead_service, name)(*args, **kwargs)


def enforce_public_intake_rate_limit(*args, **kwargs):
    return _lead_service_call("enforce_public_intake_rate_limit", *args, **kwargs)


def normalize_phone(value: str) -> str:
    from app.services import contact_service
    return contact_service.normalize_phone(value)

def create_organization(db: Session, data: OrganizationCreate) -> Organization:
    from app.services import organization_service
    return organization_service.create_organization(db, data)


def list_organizations(db: Session) -> list[Organization]:
    from app.services import organization_service
    return organization_service.list_organizations(db)


def update_organization(db: Session, org_id: UUID, data, actor_user_id: UUID | None = None) -> Organization:
    from app.services import organization_service
    return organization_service.update_organization(db, org_id, data, actor_user_id)


def require_organization(db: Session, org_id: UUID) -> Organization:
    from app.services import organization_service
    return organization_service.require_organization(db, org_id)


def scoped_get(db: Session, model, org_id: UUID, item_id: UUID):
    item = db.scalar(select(model).where(model.id == item_id, model.organization_id == org_id))
    if item is None:
        raise HTTPException(status_code=404, detail="Not found")
    return item


def create_location(db: Session, org_id: UUID, data: LocationCreate) -> Location:
    from app.services import location_service
    return location_service.create_location(db, org_id, data)


def list_locations(db: Session, org_id: UUID) -> list[Location]:
    from app.services import location_service
    return location_service.list_locations(db, org_id)


def delete_location(
    db: Session,
    org_id: UUID,
    location_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    from app.services import location_service
    return location_service.delete_location(db, org_id, location_id, actor_user_id)


def create_contact(db: Session, org_id: UUID, data: ContactCreate) -> Contact:
    from app.services import contact_service
    return contact_service.create_contact(db, org_id, data)

def list_contacts(db: Session, org_id: UUID) -> list[Contact]:
    from app.services import contact_service
    return contact_service.list_contacts(db, org_id)

def create_student(db: Session, org_id: UUID, data: StudentCreate) -> Student:
    from app.services import student_service
    return student_service.create_student(db, org_id, data)

def list_students(db: Session, org_id: UUID) -> list[Student]:
    from app.services import student_service
    return student_service.list_students(db, org_id)

def delete_student(
    db: Session,
    org_id: UUID,
    student_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    from app.services import student_service
    return student_service.delete_student(db, org_id, student_id, actor_user_id)

def attach_contact(db: Session, org_id: UUID, student_id: UUID, contact_id: UUID, relation: str | None, is_primary: bool) -> StudentContact:
    from app.services import student_service
    return student_service.attach_contact(db, org_id, student_id, contact_id, relation, is_primary)

def create_trial(db: Session, org_id: UUID, data: TrialLessonCreate, actor_user_id: UUID | None = None) -> TrialLesson:
    from app.services import trial_service
    return trial_service.create_trial(db, org_id, data, actor_user_id)


def update_trial(db: Session, org_id: UUID, trial_id: UUID, starts_at: datetime | None, location_id: UUID | None, actor_user_id: UUID | None = None) -> TrialLesson:
    from app.services import trial_service
    return trial_service.update_trial(db, org_id, trial_id, starts_at, location_id, actor_user_id)


def list_trials(db: Session, org_id: UUID) -> list[TrialLesson]:
    from app.services import trial_service
    return trial_service.list_trials(db, org_id)

def create_group(db: Session, org_id: UUID, data: GroupCreate) -> Group:
    from app.services import group_service
    return group_service.create_group(db, org_id, data)


def update_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    data: GroupUpdate,
    actor_user_id: UUID | None = None,
) -> Group:
    from app.services import group_service
    return group_service.update_group(db, org_id, group_id, data, actor_user_id)


def delete_group(
    db: Session,
    org_id: UUID,
    group_id: UUID,
    actor_user_id: UUID | None = None,
) -> None:
    from app.services import group_service
    return group_service.delete_group(db, org_id, group_id, actor_user_id)


def list_groups(db: Session, org_id: UUID) -> list[Group]:
    from app.services import group_service
    return group_service.list_groups(db, org_id)

def create_enrollment(*args, **kwargs):
    return _enrollment_service_call("create_enrollment", *args, **kwargs)


def find_intake_phone_duplicates(*args, **kwargs):
    return _lead_service_call("find_intake_phone_duplicates", *args, **kwargs)


def _append_repeat_intake_note(*args, **kwargs):
    return _lead_service_call("_append_repeat_intake_note", *args, **kwargs)


def create_intake(*args, **kwargs):
    return _lead_service_call("create_intake", *args, **kwargs)


def update_lead_details(*args, **kwargs):
    return _lead_service_call("update_lead_details", *args, **kwargs)


def update_student_crm_status(*args, **kwargs):
    return _lead_service_call("update_student_crm_status", *args, **kwargs)


def student_detail(*args, **kwargs):
    from app.services import student_service
    return student_service.student_detail(*args, **kwargs)


def complete_trial(*args, **kwargs):
    from app.services import trial_service
    return trial_service.complete_trial(*args, **kwargs)


def defer_lead(*args, **kwargs):
    return _lead_service_call("defer_lead", *args, **kwargs)


def update_lead_outcome(*args, **kwargs):
    return _lead_service_call("update_lead_outcome", *args, **kwargs)


def list_waiting_candidates(*args, **kwargs):
    return _enrollment_service_call("list_waiting_candidates", *args, **kwargs)


def form_group(*args, **kwargs):
    return _enrollment_service_call("form_group", *args, **kwargs)


def enroll_student_without_group(*args, **kwargs):
    return _enrollment_service_call("enroll_student_without_group", *args, **kwargs)


def student_profile(*args, **kwargs):
    return _enrollment_service_call("student_profile", *args, **kwargs)


def update_student_lifecycle(*args, **kwargs):
    return _enrollment_service_call("update_student_lifecycle", *args, **kwargs)


def transfer_student(*args, **kwargs):
    return _enrollment_service_call("transfer_student", *args, **kwargs)


def create_group_schedule(db: Session, org_id: UUID, data) -> GroupSchedule:
    from app.services import scheduling_service
    return scheduling_service.create_group_schedule(db, org_id, data)

def list_group_schedules(db: Session, org_id: UUID, group_id: UUID | None = None, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[GroupSchedule]:
    from app.services import scheduling_service
    return scheduling_service.list_group_schedules(db, org_id, group_id, user_id, role)

def group_roster(*args, **kwargs):
    from app.services import group_service
    return group_service.group_roster(*args, **kwargs)


def group_detail(*args, **kwargs):
    from app.services import group_service
    return group_service.group_detail(*args, **kwargs)


def _comparable_dt(value: datetime, timezone_name: str) -> datetime:
    from app.services import scheduling_service
    return scheduling_service.comparable_dt(value, timezone_name)

def _lesson_conflict_reason(
    db: Session,
    org_id: UUID,
    group: Group,
    location_id: UUID | None,
    starts_at: datetime,
    duration_minutes: int,
) -> str | None:
    from app.services import scheduling_service
    return scheduling_service.lesson_conflict_reason(
        db, org_id, group, location_id, starts_at, duration_minutes,
    )

def materialize_recurring_lesson_sessions(
    db: Session,
    org_id: UUID,
    weeks_back: int = 0,
    weeks_forward: int = 8,
) -> int:
    from app.services import scheduling_service
    return scheduling_service.materialize_recurring_lesson_sessions(
        db, org_id, weeks_back, weeks_forward,
    )

def create_lesson_session(db: Session, org_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    from app.services import scheduling_service
    return scheduling_service.create_lesson_session(db, org_id, data, user_id, role)

def list_lesson_sessions(db: Session, org_id: UUID, group_id: UUID | None = None, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> list[LessonSession]:
    from app.services import scheduling_service
    return scheduling_service.list_lesson_sessions(db, org_id, group_id, user_id, role)

def update_lesson_session(db: Session, org_id: UUID, session_id: UUID, data, user_id: UUID | None = None, role: StaffRole = StaffRole.OWNER) -> LessonSession:
    from app.services import scheduling_service
    return scheduling_service.update_lesson_session(db, org_id, session_id, data, user_id, role)

# Compatibility forwarding for the extracted attendance domain.
def _attendance_service_call(name: str, *args, **kwargs):
    from app.services import attendance_service
    return getattr(attendance_service, name)(*args, **kwargs)

def _eligible_subscription_for_session(*args, **kwargs):
    return _attendance_service_call("_eligible_subscription_for_session", *args, **kwargs)

def _attendance_should_consume(*args, **kwargs):
    return _attendance_service_call("_attendance_should_consume", *args, **kwargs)

def _sync_makeup_credit(*args, **kwargs):
    return _attendance_service_call("_sync_makeup_credit", *args, **kwargs)

def _complete_oldest_makeup(*args, **kwargs):
    return _attendance_service_call("_complete_oldest_makeup", *args, **kwargs)

def _renew_after_last_lesson(*args, **kwargs):
    return _attendance_service_call("_renew_after_last_lesson", *args, **kwargs)

def _sync_attendance_usage(*args, **kwargs):
    return _attendance_service_call("_sync_attendance_usage", *args, **kwargs)

def mark_attendance_bulk(*args, **kwargs):
    return _attendance_service_call("mark_attendance_bulk", *args, **kwargs)

def list_attendance(*args, **kwargs):
    return _attendance_service_call("list_attendance", *args, **kwargs)

def student_attendance_history(*args, **kwargs):
    return _attendance_service_call("student_attendance_history", *args, **kwargs)

def _billing_service_call(name: str, *args, **kwargs):
    from app.services import billing_service
    return getattr(billing_service, name)(*args, **kwargs)

def _payment_transactions(*args, **kwargs):
    return _billing_service_call("_payment_transactions", *args, **kwargs)

def _materialize_legacy_settlement(*args, **kwargs):
    return _billing_service_call("_materialize_legacy_settlement", *args, **kwargs)

def payment_financials(*args, **kwargs):
    return _billing_service_call("payment_financials", *args, **kwargs)

def _sync_payment_state(*args, **kwargs):
    return _billing_service_call("_sync_payment_state", *args, **kwargs)

def _attach_payment_financials(*args, **kwargs):
    return _billing_service_call("_attach_payment_financials", *args, **kwargs)

def _subscription_end_date(*args, **kwargs):
    return _billing_service_call("_subscription_end_date", *args, **kwargs)

def _lesson_unit_price(*args, **kwargs):
    return _billing_service_call("_lesson_unit_price", *args, **kwargs)

def _first_planned_lesson_date(*args, **kwargs):
    return _billing_service_call("_first_planned_lesson_date", *args, **kwargs)

def create_subscription_plan(*args, **kwargs):
    return _billing_service_call("create_subscription_plan", *args, **kwargs)

def update_subscription_plan(*args, **kwargs):
    return _billing_service_call("update_subscription_plan", *args, **kwargs)

def list_subscription_plans(*args, **kwargs):
    return _billing_service_call("list_subscription_plans", *args, **kwargs)

def create_student_subscription(*args, **kwargs):
    return _billing_service_call("create_student_subscription", *args, **kwargs)

def subscription_usage_summary(*args, **kwargs):
    return _billing_service_call("subscription_usage_summary", *args, **kwargs)

def _attach_subscription_usage(*args, **kwargs):
    return _billing_service_call("_attach_subscription_usage", *args, **kwargs)

def list_student_subscriptions(*args, **kwargs):
    return _billing_service_call("list_student_subscriptions", *args, **kwargs)

def set_subscription_auto_renew(*args, **kwargs):
    return _billing_service_call("set_subscription_auto_renew", *args, **kwargs)

def pause_subscription(*args, **kwargs):
    return _billing_service_call("pause_subscription", *args, **kwargs)

def _finish_subscription_pause(*args, **kwargs):
    return _billing_service_call("_finish_subscription_pause", *args, **kwargs)

def resume_subscription(*args, **kwargs):
    return _billing_service_call("resume_subscription", *args, **kwargs)

def _resume_due_pauses(*args, **kwargs):
    return _billing_service_call("_resume_due_pauses", *args, **kwargs)

def run_billing_renewals(*args, **kwargs):
    return _billing_service_call("run_billing_renewals", *args, **kwargs)

def create_subscription_charge(*args, **kwargs):
    return _billing_service_call("create_subscription_charge", *args, **kwargs)

def change_subscription_plan_now(*args, **kwargs):
    return _billing_service_call("change_subscription_plan_now", *args, **kwargs)

def create_payment(*args, **kwargs):
    return _billing_service_call("create_payment", *args, **kwargs)

def list_payments(*args, **kwargs):
    return _billing_service_call("list_payments", *args, **kwargs)

def add_payment_receipt(*args, **kwargs):
    return _billing_service_call("add_payment_receipt", *args, **kwargs)

def mark_payment_paid(*args, **kwargs):
    return _billing_service_call("mark_payment_paid", *args, **kwargs)

def add_payment_adjustment(*args, **kwargs):
    return _billing_service_call("add_payment_adjustment", *args, **kwargs)

def refund_payment(*args, **kwargs):
    return _billing_service_call("refund_payment", *args, **kwargs)

def list_payment_transactions(*args, **kwargs):
    return _billing_service_call("list_payment_transactions", *args, **kwargs)

def payment_summary(*args, **kwargs):
    return _billing_service_call("payment_summary", *args, **kwargs)

def cancel_payment(*args, **kwargs):
    return _billing_service_call("cancel_payment", *args, **kwargs)

def _payment_reminder_stage(*args, **kwargs):
    return _billing_service_call("_payment_reminder_stage", *args, **kwargs)

def payment_reminder_queue(*args, **kwargs):
    return _billing_service_call("payment_reminder_queue", *args, **kwargs)

def mark_payment_reminder_sent(*args, **kwargs):
    return _billing_service_call("mark_payment_reminder_sent", *args, **kwargs)

def create_staff(db: Session, org_id: UUID, data) -> Staff:
    from app.services import staff_service
    return staff_service.create_staff(db, org_id, data)


def list_staff(db: Session, org_id: UUID, active_only: bool = True) -> list[Staff]:
    from app.services import staff_service
    return staff_service.list_staff(db, org_id, active_only)


def update_staff(db: Session, org_id: UUID, staff_id: UUID, data) -> Staff:
    from app.services import staff_service
    return staff_service.update_staff(db, org_id, staff_id, data)


def set_staff_locations(db: Session, org_id: UUID, staff_id: UUID, location_ids: list[UUID]) -> Staff:
    from app.services import staff_service
    return staff_service.set_staff_locations(db, org_id, staff_id, location_ids)


def assign_staff_to_group(db: Session, org_id: UUID, staff_id: UUID, group_id: UUID, is_primary: bool = False) -> GroupStaff:
    from app.services import staff_service
    return staff_service.assign_staff_to_group(db, org_id, staff_id, group_id, is_primary)


def staff_profile(db: Session, org_id: UUID, staff_id: UUID):
    from app.services import staff_service
    return staff_service.staff_profile(db, org_id, staff_id)


def create_membership(db: Session, org_id: UUID, data):
    from app.services import staff_service
    return staff_service.create_membership(db, org_id, data)

def update_location(db: Session, org_id: UUID, location_id: UUID, data) -> Location:
    from app.services import location_service
    return location_service.update_location(db, org_id, location_id, data)


def overview_report(db: Session, org_id: UUID) -> dict:
    from app.services import reporting_service
    return reporting_service.overview_report(db, org_id)

def _workspace_service_call(name: str, *args, **kwargs):
    from app.services import workspace_service
    return getattr(workspace_service, name)(*args, **kwargs)


def _primary_contact_for_student(*args, **kwargs):
    return _workspace_service_call("_primary_contact_for_student", *args, **kwargs)


def student_preferences(*args, **kwargs):
    return _enrollment_service_call("student_preferences", *args, **kwargs)


def replace_student_preferences(*args, **kwargs):
    return _enrollment_service_call("replace_student_preferences", *args, **kwargs)


def preview_group_matches(*args, **kwargs):
    return _enrollment_service_call("preview_group_matches", *args, **kwargs)


def list_lead_overview(*args, **kwargs):
    return _workspace_service_call("list_lead_overview", *args, **kwargs)


def list_student_overview(*args, **kwargs):
    return _workspace_service_call("list_student_overview", *args, **kwargs)


def list_group_overview(*args, **kwargs):
    return _workspace_service_call("list_group_overview", *args, **kwargs)


def assigned_group_ids_for_user(*args, **kwargs):
    return _workspace_service_call("assigned_group_ids_for_user", *args, **kwargs)


def ensure_group_access(*args, **kwargs):
    return _workspace_service_call("ensure_group_access", *args, **kwargs)


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
