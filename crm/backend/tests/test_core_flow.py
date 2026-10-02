def create_org(client, name, slug):
    response = client.post("/organizations", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_public_intake_creates_student_and_contact(client):
    org = create_org(client, "AeroKiDS", "aerokids")
    response = client.post("/public/intake/aerokids", json={
        "child_first_name": "Максим",
        "child_age": 9,
        "contact_name": "Оксана",
        "phone": "0671234567",
        "comment": "Цікавиться FPV",
    })
    assert response.status_code == 201, response.text
    assert response.json()["crm_status"] == "new"
    headers = {"X-Organization-Id": org["id"]}
    students = client.get("/students", headers=headers)
    contacts = client.get("/contacts", headers=headers)
    assert len(students.json()) == 1
    assert contacts.json()[0]["phone"] == "+380671234567"


def test_tenant_isolation_on_students(client):
    org_a = create_org(client, "School A", "school-a")
    org_b = create_org(client, "School B", "school-b")
    client.post("/students", headers={"X-Organization-Id": org_a["id"]}, json={"first_name": "Anna", "age_at_inquiry": 10})
    client.post("/students", headers={"X-Organization-Id": org_b["id"]}, json={"first_name": "Bohdan", "age_at_inquiry": 11})
    a_students = client.get("/students", headers={"X-Organization-Id": org_a["id"]}).json()
    b_students = client.get("/students", headers={"X-Organization-Id": org_b["id"]}).json()
    assert [s["first_name"] for s in a_students] == ["Anna"]
    assert [s["first_name"] for s in b_students] == ["Bohdan"]


def test_cross_tenant_contact_link_is_blocked(client):
    org_a = create_org(client, "School A", "school-a")
    org_b = create_org(client, "School B", "school-b")
    student = client.post("/students", headers={"X-Organization-Id": org_a["id"]}, json={"first_name": "Anna"}).json()
    contact = client.post("/contacts", headers={"X-Organization-Id": org_b["id"]}, json={"full_name": "Other Parent", "phone": "0501234567"}).json()
    response = client.post(f"/students/{student['id']}/contacts", headers={"X-Organization-Id": org_a["id"]}, json={"contact_id": contact["id"], "relation": "parent", "is_primary": True})
    assert response.status_code == 404


def test_student_detail_and_status_update_are_tenant_scoped(client):
    org = create_org(client, "AeroKiDS", "aerokids-detail")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Максим", "age_at_inquiry": 9}).json()
    contact = client.post("/contacts", headers=headers, json={"full_name": "Оксана", "phone": "0671234567"}).json()
    client.post(
        f"/students/{student['id']}/contacts",
        headers=headers,
        json={"contact_id": contact["id"], "relation": "parent", "is_primary": True},
    )

    updated = client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "contacted"},
    )
    assert updated.status_code == 200
    assert updated.json()["crm_status"] == "contacted"

    detail = client.get(f"/students/{student['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["contacts"][0]["full_name"] == "Оксана"


def test_completed_trial_waits_for_explicit_post_trial_decision(client):
    org = create_org(client, "AeroKiDS", "aerokids-trial")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Софія", "age_at_inquiry": 10}).json()
    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={"student_id": student["id"], "starts_at": "2026-10-05T16:00:00+03:00"},
    )
    assert trial.status_code == 201, trial.text

    completed = client.patch(
        f"/trial-lessons/{trial.json()['id']}/complete",
        headers=headers,
        json={"status": "completed", "recommended_level": "starter", "teacher_notes": "Готова до групи"},
    )
    assert completed.status_code == 200, completed.text
    detail = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail["crm_status"] == "trial_completed"

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert leads.json()[0]["latest_trial_status"] == "completed"
    assert leads.json()[0]["teacher_notes"] == "Готова до групи"

    ready = client.patch(
        f"/students/{student['id']}/lead-outcome",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    assert ready.status_code == 200, ready.text
    assert ready.json()["crm_status"] == "waiting_for_group"


def test_no_show_stays_active_and_can_be_rescheduled(client):
    org = create_org(client, "AeroKiDS", "aerokids-no-show")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олег", "age_at_inquiry": 11}).json()
    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={"student_id": student["id"], "starts_at": "2026-10-06T17:00:00+03:00"},
    ).json()

    missed = client.patch(
        f"/trial-lessons/{trial['id']}/complete",
        headers=headers,
        json={"status": "no_show", "teacher_notes": "Не прийшли, телефонуємо"},
    )
    assert missed.status_code == 200, missed.text
    detail = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail["crm_status"] == "contacted"

    leads = client.get("/workspace/leads", headers=headers).json()
    assert leads[0]["latest_trial_status"] == "no_show"

    rescheduled = client.patch(
        f"/trial-lessons/{trial['id']}",
        headers=headers,
        json={"starts_at": "2026-10-08T18:00:00+03:00"},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["status"] == "scheduled"
    detail_after = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail_after["crm_status"] == "trial_scheduled"


def test_cancelled_trial_stays_active_until_rescheduled_or_closed(client):
    org = create_org(client, "AeroKiDS", "aerokids-cancelled-trial")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Назар", "age_at_inquiry": 12}).json()
    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={"student_id": student["id"], "starts_at": "2026-10-09T18:00:00+03:00"},
    ).json()

    cancelled = client.patch(
        f"/trial-lessons/{trial['id']}/complete",
        headers=headers,
        json={"status": "cancelled", "teacher_notes": "Батьки попросили інший день"},
    )
    assert cancelled.status_code == 200, cancelled.text
    detail = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail["crm_status"] == "contacted"

    leads = client.get("/workspace/leads", headers=headers).json()
    assert leads[0]["latest_trial_status"] == "cancelled"
    assert leads[0]["teacher_notes"] == "Батьки попросили інший день"

    rescheduled = client.patch(
        f"/trial-lessons/{trial['id']}",
        headers=headers,
        json={"starts_at": "2026-10-12T18:15:00+03:00"},
    )
    assert rescheduled.status_code == 200, rescheduled.text
    assert rescheduled.json()["status"] == "scheduled"


def test_lead_outcome_tracks_follow_up_and_close_reason(client):
    org = create_org(client, "AeroKiDS", "aerokids-outcome")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Ірина", "age_at_inquiry": 10}).json()

    thinking = client.patch(
        f"/students/{student['id']}/lead-outcome",
        headers=headers,
        json={
            "crm_status": "trial_completed",
            "next_contact_at": "2026-10-12T09:00:00+03:00",
        },
    )
    assert thinking.status_code == 200, thinking.text
    assert thinking.json()["next_contact_at"].startswith("2026-10-12T")

    declined = client.patch(
        f"/students/{student['id']}/lead-outcome",
        headers=headers,
        json={
            "crm_status": "declined",
            "close_reason": "schedule",
            "close_note": "Не підходять запропоновані дні",
        },
    )
    assert declined.status_code == 200, declined.text
    assert declined.json()["lead_close_reason"] == "schedule"
    assert declined.json()["next_contact_at"] is None

    missing_reason = client.patch(
        f"/students/{student['id']}/lead-outcome",
        headers=headers,
        json={"crm_status": "declined"},
    )
    assert missing_reason.status_code == 422


def test_scheduling_trial_updates_crm_status(client):
    org = create_org(client, "AeroKiDS", "aerokids-schedule")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Марко", "age_at_inquiry": 9}).json()

    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={"student_id": student["id"], "starts_at": "2026-10-07T17:30:00+03:00"},
    )
    assert trial.status_code == 201, trial.text
    detail = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail["crm_status"] == "trial_scheduled"


def test_waiting_list_and_group_formation(client):
    org = create_org(client, "AeroKiDS", "aerokids-groups")
    headers = {"X-Organization-Id": org["id"]}

    students = []
    for name, age in [("Максим", 9), ("Софія", 10)]:
        student = client.post("/students", headers=headers, json={"first_name": name, "age_at_inquiry": age}).json()
        updated = client.patch(
            f"/students/{student['id']}/crm-status",
            headers=headers,
            json={"crm_status": "waiting_for_group"},
        )
        assert updated.status_code == 200
        students.append(student)

    waiting = client.get("/waiting-list", headers=headers)
    assert waiting.status_code == 200, waiting.text
    assert {item["first_name"] for item in waiting.json()} == {"Максим", "Софія"}

    formed = client.post(
        "/groups/form",
        headers=headers,
        json={
            "name": "FPV Start 8-10",
            "capacity": 8,
            "min_age": 8,
            "max_age": 10,
            "student_ids": [student["id"] for student in students],
        },
    )
    assert formed.status_code == 201, formed.text
    assert len(formed.json()["enrolled_student_ids"]) == 2

    waiting_after = client.get("/waiting-list", headers=headers)
    assert waiting_after.status_code == 200
    assert waiting_after.json() == []

    for student in students:
        detail = client.get(f"/students/{student['id']}", headers=headers).json()
        assert detail["crm_status"] == "enrolled"
        assert detail["student_status"] == "active"


def test_group_formation_rejects_cross_tenant_student(client):
    org_a = create_org(client, "School A", "school-a-form")
    org_b = create_org(client, "School B", "school-b-form")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    student = client.post("/students", headers=b_headers, json={"first_name": "Чужий"}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=b_headers,
        json={"crm_status": "waiting_for_group"},
    )

    response = client.post(
        "/groups/form",
        headers=a_headers,
        json={"name": "Group A", "capacity": 8, "student_ids": [student["id"]]},
    )
    assert response.status_code == 404


def test_student_profile_and_transfer(client):
    org = create_org(client, "AeroKiDS", "aerokids-students")
    headers = {"X-Organization-Id": org["id"]}

    student = client.post("/students", headers=headers, json={"first_name": "Марко", "age_at_inquiry": 10}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Start", "capacity": 8, "student_ids": [student["id"]]},
    )
    assert formed.status_code == 201, formed.text

    second_group = client.post(
        "/groups",
        headers=headers,
        json={"name": "Next", "capacity": 8},
    )
    assert second_group.status_code == 201, second_group.text

    profile = client.get(f"/students/{student['id']}/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["groups"][0]["group_name"] == "Start"

    moved = client.post(
        f"/students/{student['id']}/transfer",
        headers=headers,
        json={"to_group_id": second_group.json()["id"]},
    )
    assert moved.status_code == 200, moved.text

    profile_after = client.get(f"/students/{student['id']}/profile", headers=headers)
    assert profile_after.status_code == 200
    groups = profile_after.json()["groups"]
    assert any(g["group_name"] == "Next" and g["enrollment_status"] == "active" for g in groups)
    assert any(g["group_name"] == "Start" and g["enrollment_status"] == "finished" for g in groups)


def test_student_transfer_is_tenant_scoped(client):
    org_a = create_org(client, "School A", "student-transfer-a")
    org_b = create_org(client, "School B", "student-transfer-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    student = client.post("/students", headers=a_headers, json={"first_name": "Анна"}).json()
    foreign_group = client.post("/groups", headers=b_headers, json={"name": "Foreign", "capacity": 8}).json()

    response = client.post(
        f"/students/{student['id']}/transfer",
        headers=a_headers,
        json={"to_group_id": foreign_group["id"]},
    )
    assert response.status_code == 404


def test_archiving_student_finishes_active_enrollment(client):
    org = create_org(client, "AeroKiDS", "aerokids-archive")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Іван"}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Archive Group", "capacity": 8, "student_ids": [student["id"]]},
    )

    response = client.patch(
        f"/students/{student['id']}/status",
        headers=headers,
        json={"student_status": "archived"},
    )
    assert response.status_code == 200
    assert response.json()["student_status"] == "archived"

    profile = client.get(f"/students/{student['id']}/profile", headers=headers).json()
    assert profile["groups"][0]["enrollment_status"] == "finished"


def test_schedule_session_and_attendance_flow(client):
    org = create_org(client, "AeroKiDS", "aerokids-attendance")
    headers = {"X-Organization-Id": org["id"]}

    student = client.post("/students", headers=headers, json={"first_name": "Максим", "age_at_inquiry": 9}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "FPV Start", "capacity": 8, "student_ids": [student["id"]]},
    )
    assert formed.status_code == 201, formed.text
    group_id = formed.json()["group"]["id"]

    schedule = client.post(
        "/group-schedules",
        headers=headers,
        json={"group_id": group_id, "weekday": 0, "start_time": "17:00", "duration_minutes": 60},
    )
    assert schedule.status_code == 201, schedule.text
    assert schedule.json()["weekday"] == 0

    roster = client.get(f"/groups/{group_id}/roster", headers=headers)
    assert roster.status_code == 200, roster.text
    assert roster.json()[0]["first_name"] == "Максим"

    session = client.post(
        "/lesson-sessions",
        headers=headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-10-05T17:00:00+03:00",
            "duration_minutes": 60,
            "topic": "FPV simulator",
        },
    )
    assert session.status_code == 201, session.text
    session_id = session.json()["id"]

    marked = client.put(
        f"/lesson-sessions/{session_id}/attendance",
        headers=headers,
        json={"items": [{"student_id": student["id"], "status": "present"}]},
    )
    assert marked.status_code == 200, marked.text
    assert marked.json()[0]["status"] == "present"

    attendance = client.get(f"/lesson-sessions/{session_id}/attendance", headers=headers)
    assert attendance.status_code == 200
    assert attendance.json()[0]["student_id"] == student["id"]

    sessions = client.get("/lesson-sessions", headers=headers)
    assert sessions.status_code == 200
    assert sessions.json()[0]["status"] == "completed"


def test_attendance_rejects_student_from_another_group(client):
    org = create_org(client, "AeroKiDS", "aerokids-attendance-scope")
    headers = {"X-Organization-Id": org["id"]}

    student_a = client.post("/students", headers=headers, json={"first_name": "A"}).json()
    student_b = client.post("/students", headers=headers, json={"first_name": "B"}).json()
    for student in (student_a, student_b):
        client.patch(
            f"/students/{student['id']}/crm-status",
            headers=headers,
            json={"crm_status": "waiting_for_group"},
        )

    group_a = client.post("/groups/form", headers=headers, json={"name": "A group", "capacity": 8, "student_ids": [student_a["id"]]}).json()["group"]
    client.post("/groups/form", headers=headers, json={"name": "B group", "capacity": 8, "student_ids": [student_b["id"]]})

    session = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group_a["id"], "starts_at": "2026-10-05T17:00:00+03:00"},
    ).json()

    response = client.put(
        f"/lesson-sessions/{session['id']}/attendance",
        headers=headers,
        json={"items": [{"student_id": student_b["id"], "status": "present"}]},
    )
    assert response.status_code == 409


def test_subscription_and_payment_flow(client):
    org = create_org(client, "AeroKiDS", "aerokids-payments")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Марта", "age_at_inquiry": 9}).json()

    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "8 занять", "price_minor": 180000, "period_days": 30, "lessons_included": 8},
    )
    assert plan.status_code == 201, plan.text

    subscription = client.post(
        "/student-subscriptions",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan.json()["id"],
            "starts_on": "2026-10-01",
            "discount_minor": 10000,
            "discount_label": "Знижка для сім'ї",
        },
    )
    assert subscription.status_code == 201, subscription.text
    assert subscription.json()["price_minor"] == 180000
    assert subscription.json()["discount_minor"] == 10000

    payment = client.post(
        "/payments",
        headers=headers,
        json={
            "student_id": student["id"],
            "subscription_id": subscription.json()["id"],
            "amount_minor": 170000,
            "due_date": "2000-01-01",
            "note": "Жовтень",
        },
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["status"] == "pending"

    summary = client.get("/payments-summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["pending_minor"] == 170000
    assert summary.json()["overdue_minor"] == 170000

    paid = client.patch(
        f"/payments/{payment.json()['id']}/paid",
        headers=headers,
        json={"method": "card"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["method"] == "card"
    assert paid.json()["paid_at"] is not None

    summary_after = client.get("/payments-summary", headers=headers)
    assert summary_after.json()["paid_minor"] == 170000
    assert summary_after.json()["pending_minor"] == 0


def test_atomic_subscription_charge_flow(client):
    org = create_org(client, "Atomic Billing", "atomic-billing")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олена"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Місячний", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    ).json()

    response = client.post(
        "/billing/charges",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan["id"],
            "starts_on": "2026-10-01",
            "due_date": "2026-10-05",
            "discount_minor": 20000,
            "discount_label": "Сімейна знижка",
            "note": "Жовтень",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["subscription"]["student_id"] == student["id"]
    assert body["subscription"]["plan_id"] == plan["id"]
    assert body["subscription"]["discount_minor"] == 20000
    assert body["payment"]["subscription_id"] == body["subscription"]["id"]
    assert body["payment"]["plan_id"] == plan["id"]
    assert body["payment"]["amount_minor"] == 180000
    assert body["payment"]["status"] == "pending"


def test_atomic_subscription_charge_is_tenant_scoped(client):
    org_a = create_org(client, "Atomic A", "atomic-a")
    org_b = create_org(client, "Atomic B", "atomic-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}
    student_a = client.post("/students", headers=a_headers, json={"first_name": "А"}).json()
    foreign_plan = client.post(
        "/subscription-plans",
        headers=b_headers,
        json={"name": "Foreign", "price_minor": 100000, "period_days": 30},
    ).json()

    response = client.post(
        "/billing/charges",
        headers=a_headers,
        json={
            "student_id": student_a["id"],
            "plan_id": foreign_plan["id"],
            "starts_on": "2026-10-01",
        },
    )
    assert response.status_code == 404
    subscriptions = client.get(f"/student-subscriptions?student_id={student_a['id']}", headers=a_headers)
    payments = client.get(f"/payments?student_id={student_a['id']}", headers=a_headers)
    assert subscriptions.status_code == 200
    assert subscriptions.json() == []
    assert payments.status_code == 200
    assert payments.json() == []


def test_payment_subscription_tenant_isolation(client):
    org_a = create_org(client, "School A", "payments-a")
    org_b = create_org(client, "School B", "payments-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    student_a = client.post("/students", headers=a_headers, json={"first_name": "Анна"}).json()
    plan_b = client.post(
        "/subscription-plans",
        headers=b_headers,
        json={"name": "Foreign plan", "price_minor": 100000, "period_days": 30},
    ).json()

    response = client.post(
        "/student-subscriptions",
        headers=a_headers,
        json={"student_id": student_a["id"], "plan_id": plan_b["id"], "starts_on": "2026-10-01"},
    )
    assert response.status_code == 404


def test_subscription_discount_cannot_exceed_price(client):
    org = create_org(client, "AeroKiDS", "discount-limit")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Іван"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Base", "price_minor": 100000, "period_days": 30},
    ).json()

    response = client.post(
        "/student-subscriptions",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan["id"],
            "starts_on": "2026-10-01",
            "discount_minor": 120000,
        },
    )
    assert response.status_code == 422


def test_staff_locations_groups_and_membership_flow(client):
    org = create_org(client, "AeroKiDS", "aerokids-staff")
    headers = {"X-Organization-Id": org["id"]}

    location = client.post(
        "/locations",
        headers=headers,
        json={"name": "Центр", "address": "Івано-Франківськ"},
    )
    assert location.status_code == 201, location.text

    group = client.post(
        "/groups",
        headers=headers,
        json={"name": "FPV Start", "capacity": 8, "location_id": location.json()["id"]},
    )
    assert group.status_code == 201, group.text

    staff = client.post(
        "/staff",
        headers=headers,
        json={
            "full_name": "Іван Викладач",
            "email": "teacher@example.com",
            "phone": "0671234567",
            "role": "teacher",
            "location_ids": [location.json()["id"]],
        },
    )
    assert staff.status_code == 201, staff.text
    staff_id = staff.json()["id"]

    assigned = client.post(
        f"/staff/{staff_id}/groups",
        headers=headers,
        json={"group_id": group.json()["id"], "is_primary": True},
    )
    assert assigned.status_code == 201, assigned.text
    assert assigned.json()["is_primary"] is True

    profile = client.get(f"/staff/{staff_id}/profile", headers=headers)
    assert profile.status_code == 200, profile.text
    assert profile.json()["assignments"]["location_ids"] == [location.json()["id"]]
    assert profile.json()["assignments"]["group_ids"] == [group.json()["id"]]

    membership = client.post(
        "/organization-memberships",
        headers=headers,
        json={"email": "teacher@example.com", "full_name": "Іван Викладач", "role": "teacher"},
    )
    assert membership.status_code == 201, membership.text
    assert membership.json()["role"] == "teacher"


def test_staff_assignment_rejects_foreign_location_and_group(client):
    org_a = create_org(client, "School A", "staff-scope-a")
    org_b = create_org(client, "School B", "staff-scope-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    foreign_location = client.post("/locations", headers=b_headers, json={"name": "Foreign"}).json()
    staff = client.post(
        "/staff",
        headers=a_headers,
        json={"full_name": "Manager A", "role": "manager"},
    )
    assert staff.status_code == 201

    response = client.put(
        f"/staff/{staff.json()['id']}/locations",
        headers=a_headers,
        json={"location_ids": [foreign_location["id"]]},
    )
    assert response.status_code == 404

    foreign_group = client.post("/groups", headers=b_headers, json={"name": "Foreign Group", "capacity": 8}).json()
    response_group = client.post(
        f"/staff/{staff.json()['id']}/groups",
        headers=a_headers,
        json={"group_id": foreign_group["id"], "is_primary": True},
    )
    assert response_group.status_code == 404


def test_same_user_can_have_memberships_in_multiple_organizations(client):
    org_a = create_org(client, "School A", "membership-a")
    org_b = create_org(client, "School B", "membership-b")

    ma = client.post(
        "/organization-memberships",
        headers={"X-Organization-Id": org_a["id"]},
        json={"email": "owner@example.com", "full_name": "Owner", "role": "owner"},
    )
    mb = client.post(
        "/organization-memberships",
        headers={"X-Organization-Id": org_b["id"]},
        json={"email": "owner@example.com", "full_name": "Owner", "role": "admin"},
    )
    assert ma.status_code == 201, ma.text
    assert mb.status_code == 201, mb.text
    assert ma.json()["user_id"] == mb.json()["user_id"]
    assert ma.json()["organization_id"] != mb.json()["organization_id"]


def test_overview_report_is_tenant_scoped(client):
    org_a = create_org(client, "School A", "report-a")
    org_b = create_org(client, "School B", "report-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    student_a = client.post("/students", headers=a_headers, json={"first_name": "A"}).json()
    client.patch(
        f"/students/{student_a['id']}/crm-status",
        headers=a_headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=a_headers,
        json={"name": "A Group", "capacity": 8, "student_ids": [student_a["id"]]},
    )
    assert formed.status_code == 201, formed.text

    client.post("/locations", headers=a_headers, json={"name": "A Location"})
    client.post("/staff", headers=a_headers, json={"full_name": "Teacher A", "role": "teacher"})

    student_b = client.post("/students", headers=b_headers, json={"first_name": "B"}).json()
    client.post(
        "/payments",
        headers=b_headers,
        json={"student_id": student_b["id"], "amount_minor": 99900},
    )

    report_a = client.get("/reports/overview", headers=a_headers)
    assert report_a.status_code == 200, report_a.text
    body_a = report_a.json()
    assert body_a["active_students"] == 1
    assert body_a["active_groups"] == 1
    assert body_a["enrolled_students"] == 1
    assert body_a["group_capacity"] == 8
    assert body_a["active_staff"] == 1
    assert body_a["active_locations"] == 1
    assert body_a["payments"]["pending_minor"] == 0

    report_b = client.get("/reports/overview", headers=b_headers)
    assert report_b.status_code == 200
    assert report_b.json()["payments"]["pending_minor"] == 99900
    assert report_b.json()["active_students"] == 0


def test_auth_bootstrap_login_and_me(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "aerokids-auth",
            "full_name": "Owner User",
            "email": "owner@aerokids.test",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    token = bootstrap.json()["access_token"]
    org_id = bootstrap.json()["organization_id"]

    login = client.post(
        "/auth/login",
        json={"email": "OWNER@AEROKIDS.TEST", "password": "very-secure-password"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["token_type"] == "bearer"
    assert login.json()["user"]["memberships"][0]["organization_id"] == org_id
    assert login.json()["user"]["memberships"][0]["role"] == "owner"

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "owner@aerokids.test"


def test_authenticated_user_cannot_access_another_organization(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "School A",
            "organization_slug": "auth-school-a",
            "full_name": "Owner A",
            "email": "owner-a@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    token = bootstrap.json()["access_token"]

    org_b = create_org(client, "School B", "auth-school-b")
    response = client.get(
        "/students",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": org_b["id"],
        },
    )
    assert response.status_code == 403


def test_owner_token_can_use_role_protected_staff_endpoint(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "auth-role-owner",
            "full_name": "Owner",
            "email": "owner-role@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    response = client.post(
        "/staff",
        headers=headers,
        json={"full_name": "New Teacher", "role": "teacher"},
    )
    assert response.status_code == 201, response.text


def test_bootstrap_is_single_use(client):
    first = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "bootstrap-one",
            "full_name": "Owner",
            "email": "bootstrap@example.com",
            "password": "very-secure-password",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Other",
            "organization_slug": "bootstrap-two",
            "full_name": "Other Owner",
            "email": "other@example.com",
            "password": "very-secure-password",
        },
    )
    assert second.status_code == 409


def test_owner_can_invite_teacher_and_teacher_can_accept(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "invite-school",
            "full_name": "Owner",
            "email": "owner-invite@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "teacher-invite@example.com", "role": "teacher"},
    )
    assert invite.status_code == 201, invite.text
    token = invite.json()["invite_token"]

    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": token,
            "full_name": "Teacher User",
            "password": "teacher-secure-password",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["user"]["memberships"][0]["role"] == "teacher"

    teacher_token = accepted.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {teacher_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "teacher-invite@example.com"


def test_teacher_cannot_use_owner_admin_staff_endpoint(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "role-denied-school",
            "full_name": "Owner",
            "email": "owner-denied@example.com",
            "password": "very-secure-password",
        },
    )
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }
    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "teacher-denied@example.com", "role": "teacher"},
    ).json()
    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite["invite_token"],
            "full_name": "Teacher",
            "password": "teacher-secure-password",
        },
    ).json()

    teacher_headers = {
        "Authorization": f"Bearer {accepted['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }
    denied = client.post(
        "/staff",
        headers=teacher_headers,
        json={"full_name": "Should Fail", "role": "teacher"},
    )
    assert denied.status_code == 403


def test_invitation_is_single_use(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "single-invite",
            "full_name": "Owner",
            "email": "owner-single@example.com",
            "password": "very-secure-password",
        },
    )
    headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }
    invite = client.post(
        "/organization-invitations",
        headers=headers,
        json={"email": "single-teacher@example.com", "role": "teacher"},
    ).json()

    payload = {
        "invite_token": invite["invite_token"],
        "full_name": "Teacher",
        "password": "teacher-secure-password",
    }
    assert client.post("/auth/accept-invite", json=payload).status_code == 200
    assert client.post("/auth/accept-invite", json=payload).status_code == 400


def test_workspace_overviews_return_real_tenant_data(client):
    org = create_org(client, "AeroKiDS", "workspace-overview")
    headers = {"X-Organization-Id": org["id"]}

    intake = client.post(
        "/public/intake/workspace-overview",
        json={
            "child_first_name": "Максим",
            "child_age": 9,
            "contact_name": "Оксана",
            "phone": "0671234567",
        },
    )
    assert intake.status_code == 201, intake.text

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert leads.json()[0]["first_name"] == "Максим"
    assert leads.json()[0]["contact_name"] == "Оксана"

    student_id = intake.json()["student_id"]
    client.patch(
        f"/students/{student_id}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "FPV Start", "capacity": 8, "min_age": 8, "max_age": 10, "student_ids": [student_id]},
    )
    assert formed.status_code == 201, formed.text

    students = client.get("/workspace/students", headers=headers)
    assert students.status_code == 200, students.text
    assert students.json()[0]["first_name"] == "Максим"
    assert students.json()[0]["group_name"] == "FPV Start"

    groups = client.get("/workspace/groups", headers=headers)
    assert groups.status_code == 200, groups.text
    assert groups.json()[0]["name"] == "FPV Start"
    assert groups.json()[0]["enrolled_count"] == 1
    assert groups.json()[0]["capacity"] == 8


def test_teacher_workspace_and_lessons_are_limited_to_assigned_groups(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "teacher-scope",
            "full_name": "Owner",
            "email": "owner-teacher-scope@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    students = []
    for name in ("Assigned Child", "Foreign Child"):
        student = client.post("/students", headers=owner_headers, json={"first_name": name, "age_at_inquiry": 10})
        assert student.status_code == 201, student.text
        student_id = student.json()["id"]
        client.patch(
            f"/students/{student_id}/crm-status",
            headers=owner_headers,
            json={"crm_status": "waiting_for_group"},
        )
        students.append(student_id)

    group_a = client.post(
        "/groups/form",
        headers=owner_headers,
        json={"name": "Teacher Group", "capacity": 8, "student_ids": [students[0]]},
    )
    group_b = client.post(
        "/groups/form",
        headers=owner_headers,
        json={"name": "Other Group", "capacity": 8, "student_ids": [students[1]]},
    )
    assert group_a.status_code == 201, group_a.text
    assert group_b.status_code == 201, group_b.text
    group_a_id = group_a.json()["group"]["id"]
    group_b_id = group_b.json()["group"]["id"]

    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "scoped-teacher@example.com", "role": "teacher"},
    )
    assert invite.status_code == 201, invite.text
    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Scoped Teacher",
            "password": "teacher-secure-password",
        },
    )
    assert accepted.status_code == 200, accepted.text

    staff = client.get("/staff", headers=owner_headers)
    teacher = next(item for item in staff.json() if item["email"] == "scoped-teacher@example.com")
    assigned = client.post(
        f"/staff/{teacher['id']}/groups",
        headers=owner_headers,
        json={"group_id": group_a_id, "is_primary": True},
    )
    assert assigned.status_code == 201, assigned.text

    teacher_headers = {
        "Authorization": f"Bearer {accepted.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    groups = client.get("/workspace/groups", headers=teacher_headers)
    assert groups.status_code == 200, groups.text
    assert [item["name"] for item in groups.json()] == ["Teacher Group"]

    workspace_students = client.get("/workspace/students", headers=teacher_headers)
    assert workspace_students.status_code == 200, workspace_students.text
    assert [item["first_name"] for item in workspace_students.json()] == ["Assigned Child"]

    assert client.get("/workspace/leads", headers=teacher_headers).status_code == 403
    assert client.get(f"/groups/{group_a_id}/roster", headers=teacher_headers).status_code == 200
    assert client.get(f"/groups/{group_b_id}/roster", headers=teacher_headers).status_code == 403

    allowed_session = client.post(
        "/lesson-sessions",
        headers=teacher_headers,
        json={"group_id": group_a_id, "starts_at": "2026-10-10T17:00:00+03:00"},
    )
    assert allowed_session.status_code == 201, allowed_session.text

    denied_session = client.post(
        "/lesson-sessions",
        headers=teacher_headers,
        json={"group_id": group_b_id, "starts_at": "2026-10-10T18:00:00+03:00"},
    )
    assert denied_session.status_code == 403


def test_audit_events_follow_student_workflow_and_are_tenant_scoped(client):
    org_a = create_org(client, "School A", "audit-a")
    org_b = create_org(client, "School B", "audit-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    intake = client.post(
        "/public/intake/audit-a",
        json={
            "child_first_name": "Марко",
            "child_age": 9,
            "contact_name": "Оксана",
            "phone": "0671112233",
        },
    )
    assert intake.status_code == 201, intake.text
    student_id = intake.json()["student_id"]

    client.patch(
        f"/students/{student_id}/crm-status",
        headers=a_headers,
        json={"crm_status": "contacted"},
    )
    client.post(
        "/trial-lessons",
        headers=a_headers,
        json={"student_id": student_id, "starts_at": "2026-10-12T17:00:00+03:00"},
    )

    events = client.get(
        "/audit-events",
        headers=a_headers,
        params={"entity_type": "student", "entity_id": student_id},
    )
    assert events.status_code == 200, events.text
    event_types = {item["event_type"] for item in events.json()}
    assert "lead.created" in event_types
    assert "student.crm_status_changed" in event_types
    assert "trial.scheduled" in event_types

    foreign = client.get(
        "/audit-events",
        headers=b_headers,
        params={"entity_type": "student", "entity_id": student_id},
    )
    assert foreign.status_code == 200
    assert foreign.json() == []


def test_authenticated_manual_intake_creates_real_lead(client):
    org = create_org(client, "AeroKiDS", "manual-intake")
    headers = {"X-Organization-Id": org["id"]}

    response = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Софія",
            "child_age": 10,
            "contact_name": "Марина",
            "phone": "0672223344",
            "source": "phone",
            "comment": "Зателефонували самі",
        },
    )
    assert response.status_code == 201, response.text

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert leads.json()[0]["first_name"] == "Софія"
    assert leads.json()[0]["contact_name"] == "Марина"
    assert leads.json()[0]["source"] == "phone"


def test_group_capacity_blocks_extra_enrollment_and_transfer(client):
    org = create_org(client, "AeroKiDS", "capacity-school")
    headers = {"X-Organization-Id": org["id"]}

    first = client.post("/students", headers=headers, json={"first_name": "Перший"}).json()
    second = client.post("/students", headers=headers, json={"first_name": "Другий"}).json()
    for student in (first, second):
        client.patch(
            f"/students/{student['id']}/crm-status",
            headers=headers,
            json={"crm_status": "waiting_for_group"},
        )

    full_group = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Full Group", "capacity": 1, "student_ids": [first["id"]]},
    )
    assert full_group.status_code == 201, full_group.text
    full_group_id = full_group.json()["group"]["id"]

    other_group = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Other Group", "capacity": 8, "student_ids": [second["id"]]},
    )
    assert other_group.status_code == 201, other_group.text

    transfer = client.post(
        f"/students/{second['id']}/transfer",
        headers=headers,
        json={"to_group_id": full_group_id},
    )
    assert transfer.status_code == 409
    assert "available seats" in transfer.json()["detail"]

    third = client.post("/students", headers=headers, json={"first_name": "Третій"}).json()
    enrollment = client.post(
        "/enrollments",
        headers=headers,
        json={"student_id": third["id"], "group_id": full_group_id},
    )
    assert enrollment.status_code == 409


def test_trial_can_be_rescheduled_without_creating_duplicate(client):
    org = create_org(client, "AeroKiDS", "trial-reschedule")
    headers = {"X-Organization-Id": org["id"]}
    location = client.post("/locations", headers=headers, json={"name": "Центр"}).json()
    student = client.post("/students", headers=headers, json={"first_name": "Марко"}).json()

    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={"student_id": student["id"], "starts_at": "2026-10-12T17:00:00+03:00"},
    )
    assert trial.status_code == 201, trial.text
    trial_id = trial.json()["id"]

    updated = client.patch(
        f"/trial-lessons/{trial_id}",
        headers=headers,
        json={
            "starts_at": "2026-10-13T18:30:00+03:00",
            "location_id": location["id"],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["id"] == trial_id
    assert updated.json()["location_id"] == location["id"]

    trials = client.get("/trial-lessons", headers=headers)
    assert trials.status_code == 200
    assert len(trials.json()) == 1

    events = client.get(
        "/audit-events",
        headers=headers,
        params={"entity_type": "student", "entity_id": student["id"]},
    )
    assert any(item["event_type"] == "trial.rescheduled" for item in events.json())


def test_organization_settings_are_editable_and_tenant_scoped(client):
    org_a = create_org(client, "School A", "org-settings-a")
    org_b = create_org(client, "School B", "org-settings-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    current = client.get("/organization", headers=a_headers)
    assert current.status_code == 200, current.text
    assert current.json()["timezone"] == "Europe/Kyiv"
    assert current.json()["currency"] == "UAH"
    assert current.json()["locale"] == "uk-UA"

    updated = client.patch(
        "/organization",
        headers=a_headers,
        json={
            "name": "School A International",
            "timezone": "Europe/Warsaw",
            "currency": "EUR",
            "locale": "pl-PL",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "School A International"
    assert updated.json()["timezone"] == "Europe/Warsaw"
    assert updated.json()["currency"] == "EUR"
    assert updated.json()["locale"] == "pl-PL"

    foreign = client.get("/organization", headers=b_headers)
    assert foreign.status_code == 200, foreign.text
    assert foreign.json()["name"] == "School B"
    assert foreign.json()["currency"] == "UAH"

    events = client.get(
        "/audit-events",
        headers=a_headers,
        params={"entity_type": "organization", "entity_id": org_a["id"]},
    )
    assert events.status_code == 200, events.text
    assert any(item["event_type"] == "organization.settings_updated" for item in events.json())


def test_auth_membership_returns_organization_locale_settings(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Locale School",
            "organization_slug": "locale-school",
            "full_name": "Owner",
            "email": "locale-owner@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    updated = client.patch(
        "/organization",
        headers=headers,
        json={"timezone": "Europe/Prague", "currency": "CZK", "locale": "cs-CZ"},
    )
    assert updated.status_code == 200, updated.text

    me = client.get("/auth/me", headers={"Authorization": headers["Authorization"]})
    assert me.status_code == 200, me.text
    membership = me.json()["memberships"][0]
    assert membership["organization_timezone"] == "Europe/Prague"
    assert membership["organization_currency"] == "CZK"
    assert membership["organization_locale"] == "cs-CZ"


def test_intake_accepts_explicit_international_phone_and_deduplicates_repeat(client):
    org = create_org(client, "International School", "international-intake")

    first = client.post(
        "/public/intake/international-intake",
        json={
            "child_first_name": "Ola",
            "child_age": 9,
            "contact_name": "Anna",
            "phone": "+48 501 234 567",
            "source": "website",
            "comment": "First request",
        },
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/public/intake/international-intake",
        json={
            "child_first_name": "ola",
            "child_age": 9,
            "contact_name": "Anna",
            "phone": "+48 (501) 234-567",
            "source": "website",
            "comment": "Repeated request",
        },
    )
    assert second.status_code == 201, second.text
    assert second.json()["student_id"] == first.json()["student_id"]
    assert second.json()["contact_id"] == first.json()["contact_id"]

    leads = client.get("/workspace/leads", headers={"X-Organization-Id": org["id"]})
    assert leads.status_code == 200, leads.text
    assert len(leads.json()) == 1
    assert leads.json()[0]["contact_phone"] == "+48501234567"

    events = client.get(
        "/audit-events",
        headers={"X-Organization-Id": org["id"]},
        params={"entity_type": "student", "entity_id": first.json()["student_id"]},
    )
    assert events.status_code == 200, events.text
    event_types = [item["event_type"] for item in events.json()]
    assert "lead.created" in event_types
    assert "lead.duplicate_intake" in event_types


def test_organization_currency_is_used_for_payments_and_locked_after_first_payment(client):
    org = create_org(client, "EUR School", "eur-school")
    headers = {"X-Organization-Id": org["id"]}

    updated = client.patch("/organization", headers=headers, json={"currency": "EUR"})
    assert updated.status_code == 200, updated.text

    student = client.post("/students", headers=headers, json={"first_name": "Anna"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 2500},
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["currency"] == "EUR"

    blocked = client.patch("/organization", headers=headers, json={"currency": "USD"})
    assert blocked.status_code == 409
    assert "cannot be changed" in blocked.json()["detail"]


def test_organization_rejects_unknown_timezone(client):
    org = create_org(client, "Timezone School", "timezone-school")
    response = client.patch(
        "/organization",
        headers={"X-Organization-Id": org["id"]},
        json={"timezone": "Mars/Olympus"},
    )
    assert response.status_code == 422


def test_group_formation_persists_recurring_schedule(client):
    org = create_org(client, "Schedule School", "schedule-formation")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Іра", "age_at_inquiry": 9}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )

    formed = client.post(
        "/groups/form",
        headers=headers,
        json={
            "name": "Starter",
            "capacity": 8,
            "student_ids": [student["id"]],
            "schedule_slots": [
                {"weekday": 0, "start_time": "17:00", "duration_minutes": 60},
                {"weekday": 2, "start_time": "17:00", "duration_minutes": 60},
            ],
        },
    )
    assert formed.status_code == 201, formed.text
    group_id = formed.json()["group"]["id"]

    schedules = client.get("/group-schedules", headers=headers, params={"group_id": group_id})
    assert schedules.status_code == 200, schedules.text
    assert [(item["weekday"], item["start_time"]) for item in schedules.json()] == [
        (0, "17:00:00"),
        (2, "17:00:00"),
    ]


def test_student_preferences_and_availability_are_tenant_scoped(client):
    org_a = create_org(client, "AeroKiDS A", "prefs-a")
    org_b = create_org(client, "AeroKiDS B", "prefs-b")
    a_headers = {"X-Organization-Id": org_a["id"]}
    b_headers = {"X-Organization-Id": org_b["id"]}

    location = client.post("/locations", headers=a_headers, json={"name": "Центр"}).json()
    student = client.post("/students", headers=a_headers, json={"first_name": "Марко", "age_at_inquiry": 9}).json()

    saved = client.put(
        f"/students/{student['id']}/preferences",
        headers=a_headers,
        json={
            "preferred_location_id": location["id"],
            "availability": [
                {"weekday": 0, "start_time": "16:00", "end_time": "20:00"},
                {"weekday": 2, "start_time": "16:00", "end_time": "20:00"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["preferred_location_name"] == "Центр"
    assert len(saved.json()["availability"]) == 2

    loaded = client.get(f"/students/{student['id']}/preferences", headers=a_headers)
    assert loaded.status_code == 200, loaded.text
    assert loaded.json()["availability"][0]["weekday"] == 0

    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=a_headers,
        json={"crm_status": "waiting_for_group"},
    )
    leads = client.get("/workspace/leads", headers=a_headers)
    lead = next(item for item in leads.json() if item["student_id"] == student["id"])
    assert lead["preferred_location_name"] == "Центр"
    assert len(lead["availability"]) == 2

    foreign = client.get(f"/students/{student['id']}/preferences", headers=b_headers)
    assert foreign.status_code == 404


def test_student_availability_rejects_invalid_time_range(client):
    org = create_org(client, "Availability School", "availability-invalid")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Оля"}).json()

    response = client.put(
        f"/students/{student['id']}/preferences",
        headers=headers,
        json={
            "availability": [
                {"weekday": 1, "start_time": "20:00", "end_time": "16:00"},
            ],
        },
    )
    assert response.status_code == 422


def test_audit_event_records_authenticated_actor(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Audit Actor School",
            "organization_slug": "audit-actor-school",
            "full_name": "Owner",
            "email": "audit-owner@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_id = bootstrap.json()["user_id"]
    headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    intake = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Іван",
            "child_age": 9,
            "contact_name": "Олена",
            "phone": "0675554433",
            "source": "phone",
        },
    )
    assert intake.status_code == 201, intake.text
    student_id = intake.json()["student_id"]

    changed = client.patch(
        f"/students/{student_id}/crm-status",
        headers=headers,
        json={"crm_status": "contacted"},
    )
    assert changed.status_code == 200, changed.text

    events = client.get(
        "/audit-events",
        headers=headers,
        params={"entity_type": "student", "entity_id": student_id},
    )
    assert events.status_code == 200, events.text
    actor_events = [item for item in events.json() if item["event_type"] in {"lead.created", "student.crm_status_changed"}]
    assert actor_events
    assert all(item["actor_user_id"] == owner_id for item in actor_events)


def test_public_intake_honeypot_blocks_bot_submission(client):
    org = create_org(client, "Honeypot School", "honeypot-school")
    response = client.post(
        "/public/intake/honeypot-school",
        json={
            "child_first_name": "Bot",
            "child_age": 9,
            "contact_name": "Spam",
            "phone": "0671118899",
            "website": "https://spam.example",
        },
    )
    assert response.status_code == 422

    leads = client.get("/workspace/leads", headers={"X-Organization-Id": org["id"]})
    assert leads.status_code == 200
    assert leads.json() == []


def test_public_intake_rate_limits_repeated_phone(client):
    create_org(client, "Rate Limit School", "rate-limit-school")
    payload = {
        "child_first_name": "Марко",
        "child_age": 9,
        "contact_name": "Олена",
        "phone": "0677776655",
        "source": "website",
    }

    student_id = None
    for _ in range(5):
        response = client.post("/public/intake/rate-limit-school", json=payload)
        assert response.status_code == 201, response.text
        student_id = student_id or response.json()["student_id"]
        assert response.json()["student_id"] == student_id

    blocked = client.post("/public/intake/rate-limit-school", json=payload)
    assert blocked.status_code == 429


def test_readiness_checks_database(client):
    response = client.get("/ready")
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ready", "database": "ok"}


def test_owner_can_create_single_use_password_reset_link_for_staff(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Reset School",
            "organization_slug": "reset-school",
            "full_name": "Owner",
            "email": "reset-owner@example.com",
            "password": "owner-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "reset-teacher@example.com", "role": "teacher"},
    )
    assert invite.status_code == 201, invite.text
    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Teacher",
            "password": "teacher-old-password",
        },
    )
    assert accepted.status_code == 200, accepted.text

    reset_link = client.post(
        "/password-reset-links",
        headers=owner_headers,
        json={"email": "reset-teacher@example.com"},
    )
    assert reset_link.status_code == 201, reset_link.text
    reset_token = reset_link.json()["reset_token"]

    changed = client.post(
        "/auth/reset-password",
        json={"reset_token": reset_token, "password": "teacher-new-password"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["user"]["email"] == "reset-teacher@example.com"

    old_login = client.post(
        "/auth/login",
        json={"email": "reset-teacher@example.com", "password": "teacher-old-password"},
    )
    assert old_login.status_code == 401

    new_login = client.post(
        "/auth/login",
        json={"email": "reset-teacher@example.com", "password": "teacher-new-password"},
    )
    assert new_login.status_code == 200, new_login.text

    reused = client.post(
        "/auth/reset-password",
        json={"reset_token": reset_token, "password": "another-new-password"},
    )
    assert reused.status_code == 400


def test_admin_cannot_reset_owner_password(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Owner Protected School",
            "organization_slug": "owner-protected",
            "full_name": "Owner",
            "email": "protected-owner@example.com",
            "password": "owner-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "protected-admin@example.com", "role": "admin"},
    )
    assert invite.status_code == 201, invite.text
    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Admin",
            "password": "admin-secure-password",
        },
    )
    assert accepted.status_code == 200, accepted.text

    admin_headers = {
        "Authorization": f"Bearer {accepted.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }
    blocked = client.post(
        "/password-reset-links",
        headers=admin_headers,
        json={"email": "protected-owner@example.com"},
    )
    assert blocked.status_code == 403


def test_duplicate_subscription_charge_same_period_is_rejected(client):
    org = create_org(client, "Duplicate Billing", "duplicate-billing")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олег"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Monthly", "price_minor": 180000, "period_days": 30},
    ).json()
    payload = {
        "student_id": student["id"],
        "plan_id": plan["id"],
        "starts_on": "2026-10-01",
        "due_date": "2026-10-05",
    }
    first = client.post("/billing/charges", headers=headers, json=payload)
    second = client.post("/billing/charges", headers=headers, json=payload)
    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert len(client.get(f"/payments?student_id={student['id']}", headers=headers).json()) == 1


def test_cancel_pending_charge_cancels_linked_subscription(client):
    org = create_org(client, "Cancel Billing", "cancel-billing")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Ірина"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Monthly", "price_minor": 150000, "period_days": 30},
    ).json()
    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={"student_id": student["id"], "plan_id": plan["id"], "starts_on": "2026-10-01"},
    ).json()

    cancelled = client.patch(
        f"/payments/{charge['payment']['id']}/cancel",
        headers=headers,
        json={"reason": "Створено помилково"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    subscriptions = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    assert subscriptions[0]["status"] == "cancelled"

    paid = client.patch(
        f"/payments/{charge['payment']['id']}/paid",
        headers=headers,
        json={"method": "cash"},
    )
    assert paid.status_code == 409


def test_payment_reminder_queue_is_staged_and_deduplicated(client):
    org = create_org(client, "Reminder Billing", "reminder-billing")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Марко"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 120000, "due_date": "2000-01-01"},
    ).json()

    queue = client.get("/payment-reminders", headers=headers)
    assert queue.status_code == 200, queue.text
    assert len(queue.json()) == 1
    reminder = queue.json()[0]
    assert reminder["payment_id"] == payment["id"]
    assert reminder["stage"] == "overdue_30"

    sent = client.post(
        f"/payments/{payment['id']}/reminders",
        headers=headers,
        json={"stage": "overdue_30", "channel": "phone"},
    )
    assert sent.status_code == 201, sent.text

    queue_after = client.get("/payment-reminders", headers=headers)
    assert queue_after.status_code == 200
    assert queue_after.json() == []

    duplicate = client.post(
        f"/payments/{payment['id']}/reminders",
        headers=headers,
        json={"stage": "overdue_30", "channel": "phone"},
    )
    assert duplicate.status_code == 409


def test_group_detail_contains_attendance_and_billing(client):
    org = create_org(client, "Group Detail", "group-detail")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post(
        "/students",
        headers=headers,
        json={"first_name": "Софія", "age_at_inquiry": 10},
    ).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "FPV Detail", "capacity": 8, "student_ids": [student["id"]]},
    ).json()
    group_id = formed["group"]["id"]
    session = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group_id, "starts_at": "2026-09-30T17:00:00+03:00"},
    ).json()
    client.put(
        f"/lesson-sessions/{session['id']}/attendance",
        headers=headers,
        json={"items": [{"student_id": student["id"], "status": "absent"}]},
    )
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "8 занять", "price_minor": 180000, "period_days": 30},
    ).json()
    client.post(
        "/billing/charges",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan["id"],
            "starts_on": "2026-10-01",
            "due_date": "2000-01-01",
        },
    )

    detail = client.get(f"/groups/{group_id}/detail", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["group"]["id"] == group_id
    assert len(body["members"]) == 1
    member = body["members"][0]
    assert member["student_id"] == student["id"]
    assert member["attendance"]["absent"] == 1
    assert member["attendance"]["total"] == 1
    assert member["billing"]["status"] == "overdue"
    assert member["billing"]["amount_due_minor"] == 180000
    assert len(member["payments"]) == 1
