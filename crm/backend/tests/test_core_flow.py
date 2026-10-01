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


def test_completed_trial_moves_student_to_waiting_for_group(client):
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
    assert detail["crm_status"] == "waiting_for_group"


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
