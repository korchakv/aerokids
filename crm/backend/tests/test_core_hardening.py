from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import Enrollment, EnrollmentStatus, StudentSubscription, SubscriptionStatus, SubscriptionUsage


def create_org(client, name="Hardening School", slug="hardening-school"):
    response = client.post("/organizations", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()


def headers(org):
    return {"X-Organization-Id": org["id"]}


def create_group(client, org, name="Group A", capacity=8, location_id=None):
    response = client.post("/groups", headers=headers(org), json={
        "name": name,
        "capacity": capacity,
        "location_id": location_id,
    })
    assert response.status_code == 201, response.text
    return response.json()


def create_student(client, org, name="Student"):
    response = client.post("/students", headers=headers(org), json={"first_name": name, "age_at_inquiry": 10})
    assert response.status_code == 201, response.text
    return response.json()


def create_plan(client, org, lessons=8, absent_rule="choice"):
    response = client.post("/subscription-plans", headers=headers(org), json={
        "name": f"Plan {lessons}",
        "price_minor": 200000,
        "period_days": 30,
        "lessons_included": lessons,
        "usage_mode": "attendance",
        "absent_rule": absent_rule,
        "excused_rule": "makeup",
        "late_rule": "consume",
        "end_rule": "whichever_first",
        "renewal_trigger": "last_lesson",
        "allow_debt": True,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_password_reset_invalidates_old_jwt(client):
    bootstrap = client.post("/auth/bootstrap", json={
        "organization_name": "JWT School",
        "organization_slug": "jwt-school",
        "full_name": "Owner User",
        "email": "owner-jwt@example.com",
        "password": "old-secure-password",
    })
    assert bootstrap.status_code == 201, bootstrap.text
    old_token = bootstrap.json()["access_token"]
    org_id = bootstrap.json()["organization_id"]
    auth = {"Authorization": f"Bearer {old_token}", "X-Organization-Id": org_id}

    reset_link = client.post("/password-reset-links", headers=auth, json={"email": "owner-jwt@example.com"})
    assert reset_link.status_code == 201, reset_link.text
    reset = client.post("/auth/reset-password", json={
        "reset_token": reset_link.json()["reset_token"],
        "password": "new-secure-password",
    })
    assert reset.status_code == 200, reset.text

    old_me = client.get("/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert old_me.status_code == 401
    new_me = client.get("/auth/me", headers={"Authorization": f"Bearer {reset.json()['access_token']}"})
    assert new_me.status_code == 200


def test_deactivated_staff_loses_org_access_and_role_is_synced(client):
    bootstrap = client.post("/auth/bootstrap", json={
        "organization_name": "Access School",
        "organization_slug": "access-school",
        "full_name": "Owner User",
        "email": "owner-access@example.com",
        "password": "owner-secure-password",
    }).json()
    owner_headers = {
        "Authorization": f"Bearer {bootstrap['access_token']}",
        "X-Organization-Id": bootstrap["organization_id"],
    }
    invite = client.post("/organization-invitations", headers=owner_headers, json={
        "email": "admin-access@example.com",
        "role": "admin",
        "can_teach": True,
    })
    assert invite.status_code == 201, invite.text
    accepted = client.post("/auth/accept-invite", json={
        "invite_token": invite.json()["invite_token"],
        "full_name": "Admin User",
        "password": "admin-secure-password",
    })
    assert accepted.status_code == 200, accepted.text
    admin_token = accepted.json()["access_token"]

    staff_rows = client.get("/staff", headers=owner_headers).json()
    staff = next(row for row in staff_rows if row["email"] == "admin-access@example.com")
    update = client.patch(f"/staff/{staff['id']}", headers=owner_headers, json={
        "role": "teacher",
        "is_active": False,
    })
    assert update.status_code == 200, update.text
    assert update.json()["role"] == "teacher"
    assert update.json()["is_active"] is False

    admin_org_headers = {
        "Authorization": f"Bearer {admin_token}",
        "X-Organization-Id": bootstrap["organization_id"],
    }
    assert client.get("/locations", headers=admin_org_headers).status_code == 403


def test_cross_tenant_and_unenrolled_group_billing_is_blocked(client):
    org_a = create_org(client, "School A", "billing-a")
    org_b = create_org(client, "School B", "billing-b")
    student = create_student(client, org_a, "Anna")
    plan = create_plan(client, org_a)
    own_group = create_group(client, org_a, "Own Group")
    foreign_group = create_group(client, org_b, "Foreign Group")

    cross_tenant = client.post("/billing/charges", headers=headers(org_a), json={
        "student_id": student["id"],
        "plan_id": plan["id"],
        "group_id": foreign_group["id"],
        "starts_on": date.today().isoformat(),
    })
    assert cross_tenant.status_code == 404

    not_enrolled = client.post("/billing/charges", headers=headers(org_a), json={
        "student_id": student["id"],
        "plan_id": plan["id"],
        "group_id": own_group["id"],
        "starts_on": date.today().isoformat(),
    })
    assert not_enrolled.status_code == 409


def test_schedule_edit_reconciles_future_sessions_and_get_is_read_only(client):
    org = create_org(client, "Schedule School", "schedule-hardening")
    location = client.post("/locations", headers=headers(org), json={"name": "Main"}).json()
    group = create_group(client, org, "Schedule Group", location_id=location["id"])
    today = date.today()
    old_weekday = (today.weekday() + 1) % 7
    new_weekday = (today.weekday() + 2) % 7

    added = client.post("/group-schedules", headers=headers(org), json={
        "group_id": group["id"],
        "weekday": old_weekday,
        "start_time": "10:00",
        "duration_minutes": 60,
    })
    assert added.status_code == 201, added.text
    before = client.get(f"/lesson-sessions?group_id={group['id']}", headers=headers(org)).json()
    assert any(row["status"] == "scheduled" for row in before)

    updated = client.put(f"/groups/{group['id']}", headers=headers(org), json={
        "name": "Schedule Group",
        "location_id": location["id"],
        "capacity": 8,
        "min_age": None,
        "max_age": None,
        "schedule_slots": [{
            "weekday": new_weekday,
            "start_time": "11:00",
            "duration_minutes": 60,
        }],
    })
    assert updated.status_code == 200, updated.text
    after_first_get = client.get(f"/lesson-sessions?group_id={group['id']}", headers=headers(org)).json()
    after_second_get = client.get(f"/lesson-sessions?group_id={group['id']}", headers=headers(org)).json()
    assert len(after_first_get) == len(after_second_get)
    assert any(row["status"] == "cancelled" for row in after_first_get)
    tz = ZoneInfo("Europe/Kyiv")
    scheduled = [row for row in after_first_get if row["status"] == "scheduled"]
    assert scheduled
    assert all(datetime.fromisoformat(row["starts_at"]).astimezone(tz).weekday() == new_weekday for row in scheduled)


def test_paused_student_keeps_capacity_seat(client):
    org = create_org(client, "Capacity School", "capacity-hardening")
    group = create_group(client, org, "Only Seat", capacity=1)
    first = create_student(client, org, "First")
    second = create_student(client, org, "Second")

    enrolled = client.post("/enrollments", headers=headers(org), json={
        "student_id": first["id"],
        "group_id": group["id"],
    })
    assert enrolled.status_code == 201, enrolled.text
    paused = client.patch(f"/students/{first['id']}/status", headers=headers(org), json={"student_status": "paused"})
    assert paused.status_code == 200, paused.text

    blocked = client.post("/enrollments", headers=headers(org), json={
        "student_id": second["id"],
        "group_id": group["id"],
    })
    assert blocked.status_code == 409


def test_historical_roster_allows_attendance_after_transfer(client):
    org = create_org(client, "History School", "history-hardening")
    group_a = create_group(client, org, "Old Group")
    group_b = create_group(client, org, "New Group")
    student = create_student(client, org, "History Child")
    lesson_date = date.today() - timedelta(days=2)
    transfer_date = date.today() - timedelta(days=1)
    started = lesson_date - timedelta(days=5)

    assert client.post("/enrollments", headers=headers(org), json={
        "student_id": student["id"],
        "group_id": group_a["id"],
        "started_at": started.isoformat(),
    }).status_code == 201
    lesson = client.post("/lesson-sessions", headers=headers(org), json={
        "group_id": group_a["id"],
        "starts_at": f"{lesson_date.isoformat()}T10:00:00+03:00",
        "duration_minutes": 60,
    })
    assert lesson.status_code == 201, lesson.text
    transfer = client.post(f"/students/{student['id']}/transfer", headers=headers(org), json={
        "to_group_id": group_b["id"],
        "started_at": transfer_date.isoformat(),
    })
    assert transfer.status_code == 200, transfer.text

    old_roster = client.get(
        f"/groups/{group_a['id']}/roster?at={lesson_date.isoformat()}",
        headers=headers(org),
    )
    assert old_roster.status_code == 200, old_roster.text
    assert any(row["student_id"] == student["id"] for row in old_roster.json())

    attendance = client.put(f"/lesson-sessions/{lesson.json()['id']}/attendance", headers=headers(org), json={
        "items": [{"student_id": student["id"], "status": "present"}],
    })
    assert attendance.status_code == 200, attendance.text


def test_absent_choice_is_persisted_across_finalize_and_correction(client):
    org = create_org(client, "Attendance School", "attendance-hardening")
    group = create_group(client, org, "Attendance Group")
    student = create_student(client, org, "Choice Child")
    assert client.post("/enrollments", headers=headers(org), json={
        "student_id": student["id"], "group_id": group["id"],
    }).status_code == 201
    plan = create_plan(client, org, lessons=8, absent_rule="choice")
    lesson_date = date.today() + timedelta(days=1)
    charge = client.post("/billing/charges", headers=headers(org), json={
        "student_id": student["id"],
        "plan_id": plan["id"],
        "group_id": group["id"],
        "starts_on": lesson_date.isoformat(),
    })
    assert charge.status_code == 201, charge.text
    subscription_id = charge.json()["subscription"]["id"]
    lesson = client.post("/lesson-sessions", headers=headers(org), json={
        "group_id": group["id"],
        "starts_at": f"{lesson_date.isoformat()}T12:00:00+03:00",
        "duration_minutes": 60,
    }).json()

    first = client.put(f"/lesson-sessions/{lesson['id']}/attendance", headers=headers(org), json={
        "items": [{"student_id": student["id"], "status": "absent", "consume_lesson": False}],
    })
    assert first.status_code == 200, first.text
    with SessionLocal() as db:
        usage = list(db.scalars(select(SubscriptionUsage).where(
            SubscriptionUsage.subscription_id == UUID(subscription_id),
        )))
        assert usage == []

    corrected = client.put(f"/lesson-sessions/{lesson['id']}/attendance", headers=headers(org), json={
        "items": [{"student_id": student["id"], "status": "absent", "consume_lesson": True}],
    })
    assert corrected.status_code == 200, corrected.text
    with SessionLocal() as db:
        usage = list(db.scalars(select(SubscriptionUsage).where(
            SubscriptionUsage.subscription_id == UUID(subscription_id),
        )))
        assert len(usage) == 1


def test_individual_student_can_consume_and_safely_reverse_auto_renewal(client):
    org = create_org(client, "Individual School", "individual-hardening")
    student = create_student(client, org, "Solo Child")
    activated = client.post(f"/students/{student['id']}/enroll-without-group", headers=headers(org))
    assert activated.status_code == 200, activated.text
    plan = create_plan(client, org, lessons=1)
    lesson_date = date.today() + timedelta(days=1)
    charge = client.post("/billing/charges", headers=headers(org), json={
        "student_id": student["id"],
        "plan_id": plan["id"],
        "starts_on": lesson_date.isoformat(),
        "auto_renew": True,
    })
    assert charge.status_code == 201, charge.text
    parent_id = charge.json()["subscription"]["id"]
    lesson = client.post("/individual-lessons", headers=headers(org), json={
        "student_id": student["id"],
        "starts_at": f"{lesson_date.isoformat()}T14:00:00+03:00",
        "duration_minutes": 60,
    })
    assert lesson.status_code == 201, lesson.text

    present = client.put(f"/individual-lessons/{lesson.json()['id']}/attendance", headers=headers(org), json={
        "status": "present",
    })
    assert present.status_code == 200, present.text
    with SessionLocal() as db:
        subscriptions = list(db.scalars(select(StudentSubscription).where(
            StudentSubscription.student_id == UUID(student["id"]),
        )))
        parent = next(row for row in subscriptions if str(row.id) == parent_id)
        children = [row for row in subscriptions if row.renewal_of_id == parent.id and row.status != SubscriptionStatus.CANCELLED]
        assert parent.status == SubscriptionStatus.EXPIRED
        assert len(children) == 1

    corrected = client.put(f"/individual-lessons/{lesson.json()['id']}/attendance", headers=headers(org), json={
        "status": "absent",
    })
    assert corrected.status_code == 200, corrected.text
    with SessionLocal() as db:
        subscriptions = list(db.scalars(select(StudentSubscription).where(
            StudentSubscription.student_id == UUID(student["id"]),
        )))
        parent = next(row for row in subscriptions if str(row.id) == parent_id)
        active_children = [row for row in subscriptions if row.renewal_of_id == parent.id and row.status != SubscriptionStatus.CANCELLED]
        assert parent.status == SubscriptionStatus.ACTIVE
        assert active_children == []


def test_transfer_date_belongs_only_to_target_group(client):
    org = create_org(client, slug="transfer-history")
    student = create_student(client, org, "Transfer Student")
    first = create_group(client, org, "First")
    second = create_group(client, org, "Second")
    start = date.today()
    enrolled = client.post("/enrollments", headers=headers(org), json={
        "student_id": student["id"],
        "group_id": first["id"],
        "started_at": (start - timedelta(days=2)).isoformat(),
    })
    assert enrolled.status_code == 201, enrolled.text

    moved = client.post(f"/students/{student['id']}/transfer", headers=headers(org), json={
        "to_group_id": second["id"],
        "started_at": start.isoformat(),
    })
    assert moved.status_code == 200, moved.text

    first_roster = client.get(f"/groups/{first['id']}/roster", headers=headers(org), params={"at": start.isoformat()})
    second_roster = client.get(f"/groups/{second['id']}/roster", headers=headers(org), params={"at": start.isoformat()})
    assert first_roster.status_code == 200, first_roster.text
    assert second_roster.status_code == 200, second_roster.text
    assert first_roster.json() == []
    assert [row["student_id"] for row in second_roster.json()] == [student["id"]]
