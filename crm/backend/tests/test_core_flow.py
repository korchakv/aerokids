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
