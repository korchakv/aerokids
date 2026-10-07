from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import OrgAccess, get_current_user, get_db, get_org_access, get_org_id, require_org_access_roles, require_org_roles
from app.models.core import Organization, PaymentStatus, StaffRole, User
from app.schemas import AttendanceBulkUpdate, AttendanceRead, AuditEventRead, ContactCreate, ContactRead, EnrollmentCreate, EnrollmentRead, GroupCreate, GroupDetail, GroupFormationCreate, GroupFormationResult, GroupMatchPreviewRequest, GroupMatchPreviewResponse, GroupOverviewItem, GroupRead, GroupRosterStudent, GroupScheduleCreate, GroupUpdate, GroupScheduleRead, IntakeCreate, IntakeDuplicateCheck, IntakeDuplicateResult, IntakeResult, LeadDeferUpdate, LeadDetailsUpdate, LeadListItem, LeadOutcomeUpdate, LessonSessionCreate, LessonSessionRead, LessonSessionUpdate, LocationCreate, LocationRead, LocationUpdate, OrganizationCreate, OrganizationMembershipCreate, OrganizationMembershipRead, OrganizationRead, OrganizationUpdate, OverviewReport, BillingRenewalResult, BillingRenewalRun, PaymentAdjustmentCreate, PaymentCancel, PaymentCreate, PaymentMarkPaid, PaymentRead, PaymentReceiptCreate, PaymentRefundCreate, PaymentReminderCandidate, PaymentReminderMark, PaymentSummary, PaymentTransactionRead, SubscriptionChargeCreate, SubscriptionChargeResult, StaffAssignmentInfo, StaffCreate, StaffGroupAssignment, StaffLocationAssignment, StaffProfile, StaffRead, StaffUpdate, StudentAttendanceHistoryItem, StudentContactCreate, StudentCreate, StudentDetail, StudentGroupInfo, StudentLifecycleUpdate, StudentPreferencesRead, StudentPreferencesUpdate, StudentProfile, StudentRead, StudentStatusUpdate, StudentSubscriptionCreate, StudentSubscriptionRead, StudentTransfer, SubscriptionAutoRenewUpdate, SubscriptionPauseCreate, SubscriptionPauseRead, SubscriptionResumeCreate, StudentOverviewItem, SubscriptionPlanChangeCreate, SubscriptionPlanChangeResult, SubscriptionPlanCreate, SubscriptionPlanRead, SubscriptionPlanUpdate, TrialLessonComplete, TrialLessonCreate, TrialLessonRead, TrialLessonUpdate, WaitingCandidate
from app.auth import service as auth_service
from app.auth.schemas import AcceptInvitationCreate, InvitationStatusCreate, InvitationStatusResult, AuthTokenResponse, AuthUserInfo, BootstrapOwnerCreate, BootstrapOwnerResult, BootstrapStatus, LoginCreate, OrganizationInvitationCreate, OrganizationInvitationResult, PasswordResetComplete, PasswordResetLinkCreate, PasswordResetLinkResult
from app.core.config import settings
from app.core.security import auth_is_required
from app.services import audit_service, crm, staff_service

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ready", "database": "ok"}


@router.get("/auth/bootstrap-status", response_model=BootstrapStatus)
def auth_bootstrap_status(db: Session = Depends(get_db)):
    exists = db.scalar(select(Organization.id).limit(1))
    return BootstrapStatus(available=exists is None)


@router.post("/auth/bootstrap", response_model=BootstrapOwnerResult, status_code=201)
def auth_bootstrap(
    data: BootstrapOwnerCreate,
    x_bootstrap_secret: str | None = Header(default=None, alias="X-Bootstrap-Secret"),
    db: Session = Depends(get_db),
):
    if settings.environment.lower() == "production" and x_bootstrap_secret != settings.bootstrap_secret:
        raise HTTPException(status_code=403, detail="Invalid bootstrap secret")
    organization, user, token = auth_service.bootstrap_owner(db, data)
    return BootstrapOwnerResult(
        organization_id=organization.id,
        user_id=user.id,
        access_token=token,
    )


@router.post("/auth/login", response_model=AuthTokenResponse)
def auth_login(data: LoginCreate, request: Request, db: Session = Depends(get_db)):
    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    auth_service.enforce_login_rate_limit(
        db,
        "ip",
        client_ip,
        settings.auth_login_ip_limit,
        settings.auth_login_window_minutes,
    )
    auth_service.enforce_login_rate_limit(
        db,
        "email",
        auth_service.normalize_email(data.email),
        settings.auth_login_email_limit,
        settings.auth_login_window_minutes,
    )
    token, user_info = auth_service.issue_login_token(db, data.email, data.password)
    return AuthTokenResponse(access_token=token, user=user_info)


@router.get("/auth/me", response_model=AuthUserInfo)
def auth_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return auth_service.auth_user_info(db, user)


@router.post("/organization-invitations", response_model=OrganizationInvitationResult, status_code=201)
def create_organization_invitation(
    data: OrganizationInvitationCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN)),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.role == StaffRole.OWNER and access.role != StaffRole.OWNER:
        raise HTTPException(status_code=403, detail="Only an owner can invite another owner")
    invitation, raw_token = auth_service.create_invitation(
        db, access.organization_id, user.id, data.email, data.role, data.can_teach
    )
    return OrganizationInvitationResult(
        invitation_id=invitation.id,
        email=invitation.email,
        role=invitation.role,
        can_teach=invitation.can_teach,
        invite_token=raw_token,
        expires_at=invitation.expires_at.isoformat(),
    )


@router.post("/auth/invite-status", response_model=InvitationStatusResult)
def organization_invitation_status(data: InvitationStatusCreate, db: Session = Depends(get_db)):
    return InvitationStatusResult(status=auth_service.invitation_status(db, data.invite_token))


@router.post("/auth/accept-invite", response_model=AuthTokenResponse)
def accept_organization_invitation(data: AcceptInvitationCreate, db: Session = Depends(get_db)):
    user, token, user_info = auth_service.accept_invitation(db, data.invite_token, data.full_name, data.password)
    return AuthTokenResponse(access_token=token, user=user_info)


@router.post("/password-reset-links", response_model=PasswordResetLinkResult, status_code=201)
def create_password_reset_link(
    data: PasswordResetLinkCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN)),
    db: Session = Depends(get_db),
):
    user, reset, raw_token = auth_service.create_password_reset_link(
        db,
        access.organization_id,
        access.user_id,
        access.role,
        data.email,
    )
    return PasswordResetLinkResult(
        email=user.email,
        reset_token=raw_token,
        expires_at=reset.expires_at.isoformat(),
    )


@router.post("/auth/reset-password", response_model=AuthTokenResponse)
def reset_password(data: PasswordResetComplete, db: Session = Depends(get_db)):
    user, token, user_info = auth_service.complete_password_reset(db, data.reset_token, data.password)
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


@router.get("/organization", response_model=OrganizationRead)
def current_organization(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.require_organization(db, org_id)


@router.patch("/organization", response_model=OrganizationRead)
def update_current_organization(
    data: OrganizationUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN)),
    db: Session = Depends(get_db),
):
    return crm.update_organization(db, access.organization_id, data, access.user_id)


@router.post("/locations", response_model=LocationRead, status_code=201)
def create_location(data: LocationCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return crm.create_location(db, org_id, data)


@router.get("/locations", response_model=list[LocationRead])
def locations(org_id: UUID = Depends(get_org_id), db: Session = Depends(get_db)):
    return crm.list_locations(db, org_id)


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(
    location_id: UUID,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN)),
    db: Session = Depends(get_db),
):
    crm.delete_location(db, access.organization_id, location_id, access.user_id)


@router.post("/contacts", response_model=ContactRead, status_code=201)
def create_contact(data: ContactCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.create_contact(db, org_id, data)


@router.get("/contacts", response_model=list[ContactRead])
def contacts(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.list_contacts(db, org_id)


@router.post("/students", response_model=StudentRead, status_code=201)
def create_student(data: StudentCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.create_student(db, org_id, data)


@router.get("/students", response_model=list[StudentRead])
def students(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.list_students(db, org_id)


@router.delete("/students/{student_id}", status_code=204)
def delete_student(
    student_id: UUID,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    crm.delete_student(db, access.organization_id, student_id, access.user_id)


@router.post("/students/{student_id}/contacts", status_code=201)
def add_student_contact(student_id: UUID, data: StudentContactCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    item = crm.attach_contact(db, org_id, student_id, data.contact_id, data.relation, data.is_primary)
    return {"id": str(item.id)}


@router.post("/trial-lessons", response_model=TrialLessonRead, status_code=201)
def create_trial(data: TrialLessonCreate, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.create_trial(db, access.organization_id, data, access.user_id)


@router.get("/trial-lessons", response_model=list[TrialLessonRead])
def trials(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.list_trials(db, org_id)


@router.patch("/trial-lessons/{trial_id}", response_model=TrialLessonRead)
def update_trial(
    trial_id: UUID,
    data: TrialLessonUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return crm.update_trial(db, access.organization_id, trial_id, data.starts_at, data.location_id, access.user_id)


@router.post("/groups", response_model=GroupRead, status_code=201)
def create_group(data: GroupCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.create_group(db, org_id, data)


@router.get("/groups", response_model=list[GroupRead])
def groups(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.list_groups(db, org_id)


@router.put("/groups/{group_id}", response_model=GroupRead)
def update_group(
    group_id: UUID,
    data: GroupUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return crm.update_group(db, access.organization_id, group_id, data, access.user_id)


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(
    group_id: UUID,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    crm.delete_group(db, access.organization_id, group_id, access.user_id)


@router.post("/enrollments", response_model=EnrollmentRead, status_code=201)
def create_enrollment(
    data: EnrollmentCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return crm.create_enrollment(db, access.organization_id, data, access.user_id)


@router.post("/public/intake/{organization_slug}", response_model=IntakeResult, status_code=201)
def public_intake(organization_slug: str, data: IntakeCreate, request: Request, db: Session = Depends(get_db)):
    organization = db.scalar(select(Organization).where(Organization.slug == organization_slug))
    if organization is None:
        raise HTTPException(status_code=404, detail="Organization not found")

    if data.website:
        raise HTTPException(status_code=422, detail="Invalid form submission")

    forwarded = request.headers.get("x-forwarded-for")
    client_ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    normalized_phone = crm.normalize_phone(data.phone)

    crm.enforce_public_intake_rate_limit(
        db,
        organization.id,
        "ip",
        f"{organization.id}:{client_ip}",
        settings.public_intake_ip_limit,
        settings.public_intake_window_minutes,
    )
    crm.enforce_public_intake_rate_limit(
        db,
        organization.id,
        "phone",
        f"{organization.id}:{normalized_phone}",
        settings.public_intake_phone_limit,
        settings.public_intake_window_minutes,
    )

    student, contact = crm.create_intake(db, organization, data, record_repeat=True)
    return IntakeResult(student_id=student.id, contact_id=contact.id, crm_status=student.crm_status)


@router.post("/intake/duplicate-check", response_model=IntakeDuplicateResult)
def intake_duplicate_check(
    data: IntakeDuplicateCheck,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return IntakeDuplicateResult(matches=crm.find_intake_phone_duplicates(
        db,
        access.organization_id,
        data.child_first_name,
        data.child_age,
        data.phone,
        data.child_phone,
    ))


@router.post("/intake", response_model=IntakeResult, status_code=201)
def internal_intake(
    data: IntakeCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    matches = crm.find_intake_phone_duplicates(
        db,
        access.organization_id,
        data.child_first_name,
        data.child_age,
        data.phone,
        data.child_phone,
    )
    likely_duplicate = next((item for item in matches if item["likely_same_student"]), None)
    if likely_duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "duplicate_phone",
                "message": "Такий номер уже зареєстровано. Перевірте існуючу картку учня.",
                "student_id": str(likely_duplicate["student_id"]),
            },
        )
    organization = crm.require_organization(db, access.organization_id)
    student, contact = crm.create_intake(db, organization, data, access.user_id)
    return IntakeResult(student_id=student.id, contact_id=contact.id, crm_status=student.crm_status)


@router.get("/students/{student_id}", response_model=StudentDetail)
def get_student(student_id: UUID, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    student, contacts, trials = crm.student_detail(db, org_id, student_id)
    return StudentDetail(
        **StudentRead.model_validate(student).model_dump(),
        contacts=[ContactRead.model_validate(item) for item in contacts],
        trial_lessons=[TrialLessonRead.model_validate(item) for item in trials],
    )


@router.patch("/students/{student_id}/lead-details", response_model=StudentRead)
def update_lead_details(
    student_id: UUID,
    data: LeadDetailsUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER)),
    db: Session = Depends(get_db),
):
    return crm.update_lead_details(db, access.organization_id, student_id, data, access.user_id)


@router.patch("/students/{student_id}/crm-status", response_model=StudentRead)
def update_student_status(student_id: UUID, data: StudentStatusUpdate, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.update_student_crm_status(db, access.organization_id, student_id, data.crm_status, access.user_id)


@router.patch("/students/{student_id}/defer", response_model=StudentRead)
def defer_student_lead(
    student_id: UUID,
    data: LeadDeferUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER)),
    db: Session = Depends(get_db),
):
    return crm.defer_lead(db, access.organization_id, student_id, data.deferred_until, data.reason, data.note, access.user_id)


@router.patch("/students/{student_id}/lead-outcome", response_model=StudentRead)
def update_lead_outcome(
    student_id: UUID,
    data: LeadOutcomeUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return crm.update_lead_outcome(db, access.organization_id, student_id, data, access.user_id)


@router.patch("/trial-lessons/{trial_id}/complete", response_model=TrialLessonRead)
def complete_trial(trial_id: UUID, data: TrialLessonComplete, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.complete_trial(db, access.organization_id, trial_id, data.status, data.recommended_level, data.teacher_notes, access.user_id)


@router.get("/waiting-list", response_model=list[WaitingCandidate])
def waiting_list(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.list_waiting_candidates(db, org_id)


@router.post("/groups/form", response_model=GroupFormationResult, status_code=201)
def form_group(data: GroupFormationCreate, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    group, student_ids = crm.form_group(db, access.organization_id, data, access.user_id)
    return GroupFormationResult(
        group=GroupRead.model_validate(group),
        enrolled_student_ids=student_ids,
    )


@router.post("/groups/match-preview", response_model=GroupMatchPreviewResponse)
def preview_group_matches(data: GroupMatchPreviewRequest, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return {"students": crm.preview_group_matches(db, org_id, data)}


@router.post("/students/{student_id}/enroll-without-group", response_model=StudentRead)
def enroll_student_without_group(
    student_id: UUID,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.TEACHER)),
    db: Session = Depends(get_db),
):
    return crm.enroll_student_without_group(db, access.organization_id, student_id, access.user_id)


@router.get("/students/{student_id}/profile", response_model=StudentProfile)
def get_student_profile(student_id: UUID, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    student, contacts, trials, groups = crm.student_profile(db, org_id, student_id)
    return StudentProfile(
        **StudentRead.model_validate(student).model_dump(),
        contacts=[ContactRead.model_validate(item) for item in contacts],
        trial_lessons=[TrialLessonRead.model_validate(item) for item in trials],
        groups=[StudentGroupInfo(**item) for item in groups],
    )


@router.get("/students/{student_id}/preferences", response_model=StudentPreferencesRead)
def get_student_preferences(
    student_id: UUID,
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return crm.student_preferences(db, org_id, student_id)


@router.put("/students/{student_id}/preferences", response_model=StudentPreferencesRead)
def update_student_preferences(
    student_id: UUID,
    data: StudentPreferencesUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return crm.replace_student_preferences(db, access.organization_id, student_id, data, access.user_id)


@router.patch("/students/{student_id}/status", response_model=StudentRead)
def update_student_lifecycle(student_id: UUID, data: StudentLifecycleUpdate, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.update_student_lifecycle(db, access.organization_id, student_id, data.student_status, access.user_id)


@router.post("/students/{student_id}/transfer", response_model=EnrollmentRead)
def transfer_student(student_id: UUID, data: StudentTransfer, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.transfer_student(db, access.organization_id, student_id, data.to_group_id, data.started_at, access.user_id)


@router.post("/group-schedules", response_model=GroupScheduleRead, status_code=201)
def create_group_schedule(data: GroupScheduleCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.create_group_schedule(db, org_id, data)


@router.get("/group-schedules", response_model=list[GroupScheduleRead])
def group_schedules(group_id: UUID | None = None, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.list_group_schedules(db, access.organization_id, group_id, access.user_id, access.role)


@router.get("/groups/{group_id}/roster", response_model=list[GroupRosterStudent])
def roster(group_id: UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.group_roster(db, access.organization_id, group_id, access.user_id, access.role)


@router.get("/groups/{group_id}/detail", response_model=GroupDetail)
def group_detail(group_id: UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.group_detail(db, access.organization_id, group_id, access.user_id, access.role)


@router.post("/lesson-sessions", response_model=LessonSessionRead, status_code=201)
def create_lesson_session(data: LessonSessionCreate, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.create_lesson_session(db, access.organization_id, data, access.user_id, access.role)


@router.get("/lesson-sessions", response_model=list[LessonSessionRead])
def lesson_sessions(group_id: UUID | None = None, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.list_lesson_sessions(db, access.organization_id, group_id, access.user_id, access.role)


@router.patch("/lesson-sessions/{session_id}", response_model=LessonSessionRead)
def update_lesson_session(session_id: UUID, data: LessonSessionUpdate, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.update_lesson_session(db, access.organization_id, session_id, data, access.user_id, access.role)


@router.put("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def update_attendance(session_id: UUID, data: AttendanceBulkUpdate, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.mark_attendance_bulk(db, access.organization_id, session_id, data.items, access.user_id, access.role)


@router.get("/lesson-sessions/{session_id}/attendance", response_model=list[AttendanceRead])
def attendance(session_id: UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.list_attendance(db, access.organization_id, session_id, access.user_id, access.role)


@router.get("/students/{student_id}/attendance-history", response_model=list[StudentAttendanceHistoryItem])
def student_attendance_history(student_id: UUID, access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.student_attendance_history(db, access.organization_id, student_id, access.user_id, access.role)


@router.post("/subscription-plans", response_model=SubscriptionPlanRead, status_code=201)
def create_subscription_plan(
    data: SubscriptionPlanCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.create_subscription_plan(db, access.organization_id, data, access.user_id)


@router.put("/subscription-plans/{plan_id}", response_model=SubscriptionPlanRead)
def update_subscription_plan(
    plan_id: UUID,
    data: SubscriptionPlanUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.update_subscription_plan(db, access.organization_id, plan_id, data, access.user_id)


@router.get("/subscription-plans", response_model=list[SubscriptionPlanRead])
def subscription_plans(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.list_subscription_plans(db, org_id)


@router.post("/student-subscriptions", response_model=StudentSubscriptionRead, status_code=201)
def create_student_subscription(data: StudentSubscriptionCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.create_student_subscription(db, org_id, data)


@router.get("/student-subscriptions", response_model=list[StudentSubscriptionRead])
def student_subscriptions(student_id: UUID | None = None, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.list_student_subscriptions(db, org_id, student_id)


@router.post("/student-subscriptions/{subscription_id}/change-plan", response_model=SubscriptionPlanChangeResult)
def change_subscription_plan_now(
    subscription_id: UUID,
    data: SubscriptionPlanChangeCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.change_subscription_plan_now(
        db,
        access.organization_id,
        subscription_id,
        data.plan_id,
        data.reason,
        access.user_id,
    )


@router.patch("/student-subscriptions/{subscription_id}/auto-renew", response_model=StudentSubscriptionRead)
def update_subscription_auto_renew(
    subscription_id: UUID,
    data: SubscriptionAutoRenewUpdate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.set_subscription_auto_renew(
        db,
        access.organization_id,
        subscription_id,
        data.auto_renew,
        access.user_id,
    )


@router.post("/student-subscriptions/{subscription_id}/pause", response_model=SubscriptionPauseRead, status_code=201)
def pause_student_subscription(
    subscription_id: UUID,
    data: SubscriptionPauseCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.pause_subscription(
        db,
        access.organization_id,
        subscription_id,
        data.starts_on,
        data.resume_on,
        data.note,
        access.user_id,
    )


@router.post("/student-subscriptions/{subscription_id}/resume", response_model=StudentSubscriptionRead)
def resume_student_subscription(
    subscription_id: UUID,
    data: SubscriptionResumeCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.resume_subscription(db, access.organization_id, subscription_id, data.resumes_on, access.user_id)


@router.post("/billing/renewals/run", response_model=BillingRenewalResult)
def run_billing_renewals(
    data: BillingRenewalRun,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.run_billing_renewals(db, access.organization_id, data.through_date, access.user_id)


@router.post("/billing/charges", response_model=SubscriptionChargeResult, status_code=201)
def create_subscription_charge(
    data: SubscriptionChargeCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    subscription, payment = crm.create_subscription_charge(db, access.organization_id, data, access.user_id)
    return {"subscription": subscription, "payment": payment}


@router.post("/payments", response_model=PaymentRead, status_code=201)
def create_payment(data: PaymentCreate, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.create_payment(db, access.organization_id, data, access.user_id)


@router.get("/payments", response_model=list[PaymentRead])
def payments(student_id: UUID | None = None, status: PaymentStatus | None = None, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.list_payments(db, org_id, student_id, status)


@router.post("/payments/{payment_id}/receipts", response_model=PaymentRead, status_code=201)
def add_payment_receipt(
    payment_id: UUID,
    data: PaymentReceiptCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.add_payment_receipt(
        db,
        access.organization_id,
        payment_id,
        data.amount_minor,
        data.method,
        data.paid_at,
        data.note,
        access.user_id,
    )


@router.post("/payments/{payment_id}/refunds", response_model=PaymentRead, status_code=201)
def refund_payment(
    payment_id: UUID,
    data: PaymentRefundCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.refund_payment(
        db,
        access.organization_id,
        payment_id,
        data.amount_minor,
        data.note,
        data.occurred_at,
        data.reduce_charge,
        access.user_id,
    )


@router.post("/payments/{payment_id}/adjustments", response_model=PaymentRead, status_code=201)
def adjust_payment(
    payment_id: UUID,
    data: PaymentAdjustmentCreate,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.add_payment_adjustment(
        db,
        access.organization_id,
        payment_id,
        data.direction,
        data.amount_minor,
        data.reason,
        access.user_id,
    )


@router.get("/payments/{payment_id}/transactions", response_model=list[PaymentTransactionRead])
def payment_transactions(
    payment_id: UUID,
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.list_payment_transactions(db, org_id, payment_id)


@router.patch("/payments/{payment_id}/paid", response_model=PaymentRead)
def mark_payment_paid(payment_id: UUID, data: PaymentMarkPaid, access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.mark_payment_paid(db, access.organization_id, payment_id, data.method, data.paid_at, access.user_id)


@router.patch("/payments/{payment_id}/cancel", response_model=PaymentRead)
def cancel_payment(
    payment_id: UUID,
    data: PaymentCancel,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.cancel_payment(db, access.organization_id, payment_id, data.reason, access.user_id)


@router.get("/payment-reminders", response_model=list[PaymentReminderCandidate])
def payment_reminders(
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    return crm.payment_reminder_queue(db, org_id)


@router.post("/payments/{payment_id}/reminders", status_code=201)
def mark_payment_reminder(
    payment_id: UUID,
    data: PaymentReminderMark,
    access: OrgAccess = Depends(require_org_access_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER, StaffRole.ACCOUNTANT)),
    db: Session = Depends(get_db),
):
    item = crm.mark_payment_reminder_sent(
        db,
        access.organization_id,
        payment_id,
        data.stage,
        data.channel,
        access.user_id,
    )
    return {"id": str(item.id), "payment_id": str(item.payment_id), "stage": item.stage, "sent_at": item.sent_at}


@router.get("/payments-summary", response_model=PaymentSummary)
def payments_summary(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.ACCOUNTANT)), db: Session = Depends(get_db)):
    return crm.payment_summary(db, org_id)


@router.post("/staff", response_model=StaffRead, status_code=201)
def create_staff(data: StaffCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return staff_service.create_staff(db, org_id, data)


@router.get("/staff", response_model=list[StaffRead])
def staff(active_only: bool = True, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return staff_service.list_staff(db, org_id, active_only)


@router.patch("/staff/{staff_id}", response_model=StaffRead)
def update_staff(staff_id: UUID, data: StaffUpdate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return staff_service.update_staff(db, org_id, staff_id, data)


@router.get("/staff/{staff_id}/profile", response_model=StaffProfile)
def get_staff_profile(staff_id: UUID, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    item, location_ids, group_ids = staff_service.staff_profile(db, org_id, staff_id)
    return StaffProfile(
        **StaffRead.model_validate(item).model_dump(),
        assignments=StaffAssignmentInfo(location_ids=location_ids, group_ids=group_ids),
    )


@router.put("/staff/{staff_id}/locations", response_model=StaffRead)
def update_staff_locations(staff_id: UUID, data: StaffLocationAssignment, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    return staff_service.set_staff_locations(db, org_id, staff_id, data.location_ids)


@router.post("/staff/{staff_id}/groups", status_code=201)
def assign_staff_group(staff_id: UUID, data: StaffGroupAssignment, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)), db: Session = Depends(get_db)):
    item = staff_service.assign_staff_to_group(db, org_id, staff_id, data.group_id, data.is_primary)
    return {"id": str(item.id), "group_id": str(item.group_id), "is_primary": item.is_primary}


@router.post("/organization-memberships", response_model=OrganizationMembershipRead, status_code=201)
def create_organization_membership(data: OrganizationMembershipCreate, org_id: UUID = Depends(require_org_roles(StaffRole.OWNER)), db: Session = Depends(get_db)):
    membership, user = staff_service.create_membership(db, org_id, data)
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
def workspace_leads(org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)), db: Session = Depends(get_db)):
    return crm.list_lead_overview(db, org_id)


@router.get("/workspace/students", response_model=list[StudentOverviewItem])
def workspace_students(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.list_student_overview(db, access.organization_id, access.user_id, access.role)


@router.get("/workspace/groups", response_model=list[GroupOverviewItem])
def workspace_groups(access: OrgAccess = Depends(get_org_access), db: Session = Depends(get_db)):
    return crm.list_group_overview(db, access.organization_id, access.user_id, access.role)


@router.delete("/staff/{staff_id}/groups/{group_id}", status_code=204)
def remove_staff_group(
    staff_id: UUID,
    group_id: UUID,
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN)),
    db: Session = Depends(get_db),
):
    crm.remove_staff_from_group(db, org_id, staff_id, group_id)


@router.get("/audit-events", response_model=list[AuditEventRead])
def audit_events(
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    limit: int = 100,
    org_id: UUID = Depends(require_org_roles(StaffRole.OWNER, StaffRole.ADMIN, StaffRole.MANAGER)),
    db: Session = Depends(get_db),
):
    return audit_service.list_audit_events(db, org_id, entity_type, entity_id, min(max(limit, 1), 500))
