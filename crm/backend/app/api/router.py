from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db, get_org_id, require_org_roles
from app.models.core import Organization, PaymentStatus, StaffRole, User
from app.schemas import AttendanceBulkUpdate, AttendanceRead, ContactCreate, ContactRead, EnrollmentCreate, EnrollmentRead, GroupCreate, GroupFormationCreate, GroupFormationResult, GroupOverviewItem, GroupRead, GroupRosterStudent, GroupScheduleCreate, GroupScheduleRead, IntakeCreate, IntakeResult, LeadListItem, LessonSessionCreate, LessonSessionRead, LocationCreate, LocationRead, LocationUpdate, OrganizationCreate, OrganizationMembershipCreate, OrganizationMembershipRead, OrganizationRead, OverviewReport, PaymentCreate, PaymentMarkPaid, PaymentRead, PaymentSummary, StaffAssignmentInfo, StaffCreate, StaffGroupAssignment, StaffLocationAssignment, StaffProfile, StaffRead, StaffUpdate, StudentContactCreate, StudentCreate, StudentDetail, StudentGroupInfo, StudentLifecycleUpdate, StudentProfile, StudentRead, StudentStatusUpdate, StudentSubscriptionCreate, StudentSubscriptionRead, StudentTransfer, StudentOverviewItem, SubscriptionPlanCreate, SubscriptionPlanRead, TrialLessonComplete, TrialLessonCreate, TrialLessonRead, WaitingCandidate
from app.auth import service as auth_service
from app.auth.schemas import AcceptInvitationCreate, AuthTokenResponse, AuthUserInfo, BootstrapOwnerCreate, BootstrapOwnerResult, LoginCreate, OrganizationInvitationCreate, OrganizationInvitationResult
from app.core.security import auth_is_required
from app.services import crm

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/auth/bootstrap", response_model=BootstrapOwnerResult, status_code=201)
def auth_bootstrap(data: BootstrapOwnerCreate, db: Session = Depends(get_db)):
    organization, user, token = auth_service.bootstrap_owner(db, data)
    return BootstrapOwnerResult(
        organization_id=organization.id,
        user_id=user.id,
        access_token=token,
    )


@router.post("/auth/login", response_model=AuthTokenResponse)
def auth_login(data: LoginCreate, db: Session = Depends(get_db)):
    token, user_info = auth_service.issue_login_token(db, data.email, data.password)
    return AuthTokenResponse(access_token=token, user=user_info)


@router.get("/auth/me", response_model=AuthUserInfo)
def auth_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return auth_service.auth_user_info(db, user)


@router.post("/organization-invitations", response_model=OrganizationInvitationResult, status_code=201)
def create_organization_invitation(
    data: OrganizationInvitationCreate,
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitation, raw_token = auth_service.create_invitation(db, org_id, user.id, data.email, data.role)
    return OrganizationInvitationResult(
        invitation_id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        invite_token=raw_token,
        expires_at=invitation.expires_at.isoformat(),
    )


@router.post("/auth/accept-invite", response_model=AuthTokenResponse)
def accept_organization_invitation(data: AcceptInvitationCreate, db: Session = Depends(get_db)):
    user, token, user_info = auth_service.accept_invitation(db, data.invite_token, data.full_name, data.password)
    return AuthTokenResponse(access_token=token, user=user_info)


@router.post("/organizations", response_model=OrganizationRead, status_code=201)
def create_organization(data: OrganizationCreate, db: Session = Depends(get_db)):
    if auth_is_required():
        raise HTTPException(status_code=403, detail="Direct organization creation is disabled when authentication is required")
    return crm.create_organization(db, data)


@router.get("/organizations", response_model=list[OrganizationRead])
def organizations(db: Session = Depends(get_db)):
    if auth_is_required():
        raise HTTPException(status_code=403, detail="Use /auth/me to list your organizations")
    return crm.list_organizations(db)


@router.post("/locations", response_model=LocationRead, status_code=201)
def create_location(data: LocationCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
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


@router.get("/students/{student_id}", response_model=StudentDetail)
def get_student(student_id: UUID, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    student, contacts, trials = crm.student_detail(db, org_id, student_id)
    return StudentDetail(
        **StudentRead.model_validate(student).model_dump(),
        contacts=[ContactRead.model_validate(item) for item in contacts],
        trial_lessons=[TrialLessonRead.model_validate(item) for item in trials],
    )


@router.patch("/students/{student_id}/crm-status", response_model=StudentRead)
def update_student_status(student_id: UUID, data: StudentStatusUpdate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.update_student_crm_status(db, org_id, student_id, data.crm_status)


@router.patch("/trial-lessons/{trial_id}/complete", response_model=TrialLessonRead)
def complete_trial(trial_id: UUID, data: TrialLessonComplete, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.complete_trial(db, org_id, trial_id, data.status, data.recommended_level, data.teacher_notes)


@router.get("/waiting-list", response_model=list[WaitingCandidate])
def waiting_list(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_waiting_candidates(db, org_id)


@router.post("/groups/form", response_model=GroupFormationResult, status_code=201)
def form_group(data: GroupFormationCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    group, student_ids = crm.form_group(db, org_id, data)
    return GroupFormationResult(
        group=GroupRead.model_validate(group),
        enrolled_student_ids=student_ids,
    )


@router.get("/students/{student_id}/profile", response_model=StudentProfile)
def get_student_profile(student_id: UUID, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    student, contacts, trials, groups = crm.student_profile(db, org_id, student_id)
    return StudentProfile(
        **StudentRead.model_validate(student).model_dump(),
        contacts=[ContactRead.model_validate(item) for item in contacts],
        trial_lessons=[TrialLessonRead.model_validate(item) for item in trials],
        groups=[StudentGroupInfo(**item) for item in groups],
    )


@router.patch("/students/{student_id}/status", response_model=StudentRead)
def update_student_lifecycle(student_id: UUID, data: StudentLifecycleUpdate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.update_student_lifecycle(db, org_id, student_id, data.student_status)


@router.post("/students/{student_id}/transfer", response_model=EnrollmentRead)
def transfer_student(student_id: UUID, data: StudentTransfer, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.transfer_student(db, org_id, student_id, data.to_group_id, data.started_at)


@router.post("/group-schedules", response_model=GroupScheduleRead, status_code=201)
def create_group_schedule(data: GroupScheduleCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_group_schedule(db, org_id, data)


@router.get("/group-schedules", response_model=list[GroupScheduleRead])
def group_schedules(group_id: UUID | None = None, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_group_schedules(db, org_id, group_id)


@router.get("/groups/{group_id}/roster", response_model=list[GroupRosterStudent])
def roster(group_id: UUID, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.group_roster(db, org_id, group_id)


@router.post("/lesson-sessions", response_model=LessonSessionRead, status_code=201)
def create_lesson_session(data: LessonSessionCreate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.create_lesson_session(db, org_id, data)


@router.get("/lesson-sessions", response_model=list[LessonSessionRead])
def lesson_sessions(group_id: UUID | None = None, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_lesson_sessions(db, org_id, group_id)


@router.put("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def update_attendance(session_id: UUID, data: AttendanceBulkUpdate, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.mark_attendance_bulk(db, org_id, session_id, data.items)


@router.get("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def attendance(session_id: UUID, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_attendance(db, org_id, session_id)


@router.post("/subscription-plans", response_model=SubscriptionPlanRead, status_code=201)
def create_subscription_plan(data: SubscriptionPlanCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.create_subscription_plan(db, org_id, data)


@router.get("/subscription-plans", response_model=list[SubscriptionPlanRead])
def subscription_plans(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_subscription_plans(db, org_id)


@router.post("/student-subscriptions", response_model=StudentSubscriptionRead, status_code=201)
def create_student_subscription(data: StudentSubscriptionCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.create_student_subscription(db, org_id, data)


@router.get("/student-subscriptions", response_model=list[StudentSubscriptionRead])
def student_subscriptions(student_id: UUID | None = None, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_student_subscriptions(db, org_id, student_id)


@router.post("/payments", response_model=PaymentRead, status_code=201)
def create_payment(data: PaymentCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.create_payment(db, org_id, data)


@router.get("/payments", response_model=list[PaymentRead])
def payments(student_id: UUID | None = None, status: PaymentStatus | None = None, org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_payments(db, org_id, student_id, status)


@router.patch("/payments/{payment_id}/paid", response_model=PaymentRead)
def mark_payment_paid(payment_id: UUID, data: PaymentMarkPaid, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.mark_payment_paid(db, org_id, payment_id, data.method, data.paid_at)


@router.get("/payments-summary", response_model=PaymentSummary)
def payments_summary(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.payment_summary(db, org_id)


@router.post("/staff", response_model=StaffRead, status_code=201)
def create_staff(data: StaffCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return crm.create_staff(db, org_id, data)


@router.get("/staff", response_model=list[StaffRead])
def staff(active_only: bool = True, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return crm.list_staff(db, org_id, active_only)


@router.patch("/staff/{staff_id}", response_model=StaffRead)
def update_staff(staff_id: UUID, data: StaffUpdate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return crm.update_staff(db, org_id, staff_id, data)


@router.get("/staff/{staff_id}/profile", response_model=StaffProfile)
def get_staff_profile(staff_id: UUID, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    item, location_ids, group_ids = crm.staff_profile(db, org_id, staff_id)
    return StaffProfile(
        **StaffRead.model_validate(item).model_dump(),
        assignments=StaffAssignmentInfo(location_ids=location_ids, group_ids=group_ids),
    )


@router.put("/staff/{staff_id}/locations", response_model=StaffRead)
def update_staff_locations(staff_id: UUID, data: StaffLocationAssignment, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return crm.set_staff_locations(db, org_id, staff_id, data.location_ids)


@router.post("/staff/{staff_id}/groups", status_code=201)
def assign_staff_group(staff_id: UUID, data: StaffGroupAssignment, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    item = crm.assign_staff_to_group(db, org_id, staff_id, data.group_id, data.is_primary)
    return {"id": str(item.id), "group_id": str(item.group_id), "is_primary": item.is_primary}


@router.post("/organization-memberships", response_model=OrganizationMembershipRead, status_code=201)
def create_organization_membership(data: OrganizationMembershipCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER)), db: Session = Depends(get_db)):
    membership, user = crm.create_membership(db, org_id, data)
    return OrganizationMembershipRead(
        id=membership.id,
        organization_id=membership.organization_id,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=membership.role,
        is_active=membership.is_active,
    )


@router.patch("/locations/{location_id}", response_model=LocationRead)
def update_location(location_id: UUID, data: LocationUpdate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return crm.update_location(db, org_id, location_id, data)


@router.get("/reports/overview", response_model=OverviewReport)
def report_overview(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.overview_report(db, org_id)


@router.get("/workspace/leads", response_model=list[LeadListItem])
def workspace_leads(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_lead_overview(db, org_id)


@router.get("/workspace/students", response_model=list[StudentOverviewItem])
def workspace_students(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_student_overview(db, org_id)


@router.get("/workspace/groups", response_model=list[GroupOverviewItem])
def workspace_groups(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_group_overview(db, org_id)
