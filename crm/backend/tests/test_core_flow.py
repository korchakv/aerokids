from datetime import date, timedelta

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


def test_lead_can_be_deferred_and_returned_to_work(client):
    org = create_org(client, "Deferred Leads", "deferred-leads")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олена", "age_at_inquiry": 10}).json()

    deferred = client.patch(
        f"/students/{student['id']}/defer",
        headers=headers,
        json={
            "deferred_until": "2035-04-06T10:00:00+03:00",
            "reason": "later",
            "note": "Написати навесні",
        },
    )
    assert deferred.status_code == 200, deferred.text
    assert deferred.json()["deferred_until"].startswith("2035-04-06T")
    assert deferred.json()["deferred_reason"] == "later"
    assert deferred.json()["next_contact_at"].startswith("2035-04-06T")

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    row = next(item for item in leads.json() if item["student_id"] == student["id"])
    assert row["deferred_reason"] == "later"
    assert row["deferred_note"] == "Написати навесні"

    resumed = client.patch(
        f"/students/{student['id']}/defer",
        headers=headers,
        json={"deferred_until": None},
    )
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["deferred_until"] is None
    assert resumed.json()["next_contact_at"] is None


def test_lead_defer_rejects_past_date(client):
    org = create_org(client, "Deferred Past", "deferred-past")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Тарас"}).json()

    response = client.patch(
        f"/students/{student['id']}/defer",
        headers=headers,
        json={"deferred_until": "2020-01-01T10:00:00+02:00", "reason": "later"},
    )
    assert response.status_code == 422, response.text


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


def test_new_lead_can_be_enrolled_directly(client):
    org = create_org(client, "Direct Enrollment", "direct-enrollment")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Нова", "age_at_inquiry": 9}).json()
    group = client.post("/groups", headers=headers, json={"name": "Direct Group", "capacity": 8}).json()

    enrolled = client.post("/enrollments", headers=headers, json={
        "student_id": student["id"],
        "group_id": group["id"],
        "started_at": "2026-10-03",
    })
    assert enrolled.status_code == 201, enrolled.text

    detail = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail["crm_status"] == "enrolled"
    assert detail["student_status"] == "active"


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


def test_empty_group_can_be_created_with_schedule(client):
    org = create_org(client, "Precreated Groups", "precreated-groups")
    headers = {"X-Organization-Id": org["id"]}

    response = client.post(
        "/groups/form",
        headers=headers,
        json={
            "name": "Ранкова група",
            "capacity": 8,
            "student_ids": [],
            "schedule_slots": [
                {"weekday": 1, "start_time": "10:00", "duration_minutes": 60},
                {"weekday": 3, "start_time": "10:00", "duration_minutes": 60},
            ],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["enrolled_student_ids"] == []
    group_id = payload["group"]["id"]

    schedules = client.get(f"/group-schedules?group_id={group_id}", headers=headers)
    assert schedules.status_code == 200, schedules.text
    assert len(schedules.json()) == 2
    assert {item["weekday"] for item in schedules.json()} == {1, 3}


def test_group_can_be_edited_with_location_capacity_and_schedule(client):
    org = create_org(client, "Editable Groups", "editable-groups")
    headers = {"X-Organization-Id": org["id"]}
    location = client.post(
        "/locations",
        headers=headers,
        json={"name": "Центр", "address": "Івано-Франківськ"},
    )
    assert location.status_code == 201, location.text

    formed = client.post(
        "/groups/form",
        headers=headers,
        json={
            "name": "Помилкова назва",
            "capacity": 8,
            "schedule_slots": [
                {"weekday": 1, "start_time": "10:00", "duration_minutes": 60},
                {"weekday": 3, "start_time": "10:00", "duration_minutes": 60},
            ],
        },
    )
    assert formed.status_code == 201, formed.text
    group_id = formed.json()["group"]["id"]

    updated = client.put(
        f"/groups/{group_id}",
        headers=headers,
        json={
            "name": "FPV Вечір",
            "capacity": 10,
            "location_id": location.json()["id"],
            "schedule_slots": [
                {"weekday": 0, "start_time": "18:15", "duration_minutes": 60},
                {"weekday": 4, "start_time": "18:15", "duration_minutes": 90},
            ],
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "FPV Вечір"
    assert updated.json()["capacity"] == 10
    assert updated.json()["location_id"] == location.json()["id"]

    schedules = client.get(f"/group-schedules?group_id={group_id}", headers=headers)
    assert schedules.status_code == 200, schedules.text
    assert {(item["weekday"], item["start_time"][:5], item["duration_minutes"]) for item in schedules.json()} == {
        (0, "18:15", 60),
        (4, "18:15", 90),
    }

    # Re-enable a previously used slot: the unique DB row should be reused, not duplicated.
    restored = client.put(
        f"/groups/{group_id}",
        headers=headers,
        json={
            "name": "FPV Вечір",
            "capacity": 10,
            "location_id": location.json()["id"],
            "schedule_slots": [
                {"weekday": 1, "start_time": "10:00", "duration_minutes": 75},
            ],
        },
    )
    assert restored.status_code == 200, restored.text
    restored_schedules = client.get(f"/group-schedules?group_id={group_id}", headers=headers)
    assert restored_schedules.status_code == 200, restored_schedules.text
    assert [(item["weekday"], item["start_time"][:5], item["duration_minutes"]) for item in restored_schedules.json()] == [
        (1, "10:00", 75),
    ]


def test_empty_group_can_be_deleted_without_losing_history_tables(client):
    org = create_org(client, "Delete Empty Group", "delete-empty-group")
    headers = {"X-Organization-Id": org["id"]}

    formed = client.post(
        "/groups/form",
        headers=headers,
        json={
            "name": "Помилкова група",
            "capacity": 8,
            "schedule_slots": [{"weekday": 2, "start_time": "17:00", "duration_minutes": 60}],
        },
    )
    assert formed.status_code == 201, formed.text
    group_id = formed.json()["group"]["id"]

    deleted = client.delete(f"/groups/{group_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    visible_groups = client.get("/workspace/groups", headers=headers)
    assert visible_groups.status_code == 200, visible_groups.text
    assert all(item["group_id"] != group_id for item in visible_groups.json())

    schedules = client.get(f"/group-schedules?group_id={group_id}", headers=headers)
    assert schedules.status_code == 404, schedules.text


def test_empty_group_with_unfinished_lesson_placeholder_can_be_deleted(client):
    org = create_org(client, "Delete Draft Lesson Group", "delete-draft-lesson-group")
    headers = {"X-Organization-Id": org["id"]}

    group = client.post(
        "/groups",
        headers=headers,
        json={"name": "12", "capacity": 8},
    )
    assert group.status_code == 201, group.text
    group_id = group.json()["id"]

    lesson = client.post(
        "/lesson-sessions",
        headers=headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-10-05T17:00:00+03:00",
            "duration_minutes": 60,
            "topic": "Заняття",
        },
    )
    assert lesson.status_code == 201, lesson.text
    lesson_id = lesson.json()["id"]
    assert lesson.json()["status"] == "scheduled"

    deleted = client.delete(f"/groups/{group_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    groups = client.get("/workspace/groups", headers=headers)
    assert groups.status_code == 200, groups.text
    assert all(item["group_id"] != group_id for item in groups.json())

    lessons = client.get("/lesson-sessions", headers=headers)
    assert lessons.status_code == 200, lessons.text
    assert all(item["id"] != lesson_id for item in lessons.json())


def test_group_delete_is_blocked_while_students_are_enrolled(client):
    org = create_org(client, "Protected Group Delete", "protected-group-delete")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олег", "age_at_inquiry": 10}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Активна група", "capacity": 8, "student_ids": [student["id"]]},
    )
    assert formed.status_code == 201, formed.text

    deleted = client.delete(f"/groups/{formed.json()['group']['id']}", headers=headers)
    assert deleted.status_code == 409, deleted.text
    assert "учні" in deleted.json()["detail"].lower()


def test_location_can_be_edited_and_deleted_when_unused(client):
    org = create_org(client, "Editable Locations", "editable-locations")
    headers = {"X-Organization-Id": org["id"]}
    created = client.post(
        "/locations",
        headers=headers,
        json={"name": "Стара назва", "address": "Стара адреса"},
    )
    assert created.status_code == 201, created.text
    location_id = created.json()["id"]

    updated = client.patch(
        f"/locations/{location_id}",
        headers=headers,
        json={"name": "Нова назва", "address": "Нова адреса"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Нова назва"
    assert updated.json()["address"] == "Нова адреса"

    deleted = client.delete(f"/locations/{location_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    locations = client.get("/locations", headers=headers)
    assert locations.status_code == 200, locations.text
    assert all(item["id"] != location_id for item in locations.json())


def test_location_delete_is_blocked_while_active_group_uses_it(client):
    org = create_org(client, "Protected Location Delete", "protected-location-delete")
    headers = {"X-Organization-Id": org["id"]}
    location = client.post("/locations", headers=headers, json={"name": "Центр"}).json()
    group = client.post(
        "/groups",
        headers=headers,
        json={"name": "Центр група", "capacity": 8, "location_id": location["id"]},
    )
    assert group.status_code == 201, group.text

    deleted = client.delete(f"/locations/{location['id']}", headers=headers)
    assert deleted.status_code == 409, deleted.text
    assert "використовує група" in deleted.json()["detail"].lower()


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


def test_student_without_history_can_be_deleted(client):
    org = create_org(client, "Delete Student", "delete-student")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post(
        "/students",
        headers=headers,
        json={"first_name": "Помилковий", "age_at_inquiry": 10},
    )
    assert student.status_code == 201, student.text
    student_id = student.json()["id"]

    deleted = client.delete(f"/students/{student_id}", headers=headers)
    assert deleted.status_code == 204, deleted.text

    students = client.get("/students", headers=headers)
    assert students.status_code == 200, students.text
    assert all(item["id"] != student_id for item in students.json())


def test_student_delete_is_blocked_after_enrollment(client):
    org = create_org(client, "Protected Student Delete", "protected-student-delete")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Історія"}).json()
    client.patch(
        f"/students/{student['id']}/crm-status",
        headers=headers,
        json={"crm_status": "waiting_for_group"},
    )
    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "History Group", "capacity": 8, "student_ids": [student["id"]]},
    )
    assert formed.status_code == 201, formed.text

    deleted = client.delete(f"/students/{student['id']}", headers=headers)
    assert deleted.status_code == 409, deleted.text
    assert "архів" in deleted.json()["detail"].lower()


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

    updated_lesson = client.patch(
        f"/lesson-sessions/{session_id}",
        headers=headers,
        json={"topic": "FPV gates", "notes": "Домашня траса: 3 кола без падіння"},
    )
    assert updated_lesson.status_code == 200, updated_lesson.text
    assert updated_lesson.json()["topic"] == "FPV gates"
    assert updated_lesson.json()["notes"] == "Домашня траса: 3 кола без падіння"

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
    completed = next(item for item in sessions.json() if item["id"] == session_id)
    assert completed["status"] == "completed"


def test_recurring_schedule_materializes_concrete_lessons(client):
    org = create_org(client, "Recurring School", "recurring-lessons")
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
        json={"name": "Tech Group", "capacity": 8, "student_ids": [student["id"]]},
    )
    assert formed.status_code == 201, formed.text
    group_id = formed.json()["group"]["id"]

    schedule = client.post(
        "/group-schedules",
        headers=headers,
        json={"group_id": group_id, "weekday": 0, "start_time": "17:00", "duration_minutes": 60},
    )
    assert schedule.status_code == 201, schedule.text

    first = client.get("/lesson-sessions", headers=headers)
    assert first.status_code == 200, first.text
    generated = [item for item in first.json() if item["group_id"] == group_id]
    assert len(generated) >= 8
    assert all(item["duration_minutes"] == 60 for item in generated)

    second = client.get("/lesson-sessions", headers=headers)
    assert second.status_code == 200, second.text
    assert len(second.json()) == len(first.json())


def test_attendance_rejects_student_from_another_group(client):
    org = create_org(client, "AeroKiDS", "aerokids-attendance-scope")
    headers = {"X-Organization-Id": org["id"]}

    student_a = client.post("/students", headers=headers, json={"first_name": "Anna"}).json()
    student_b = client.post("/students", headers=headers, json={"first_name": "Bohdan"}).json()
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


def test_attendance_consumes_subscription_and_creates_makeup(client):
    org = create_org(client, "Usage School", "usage-school")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Оля"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    group_id = client.post("/groups/form", headers=headers, json={"name": "Usage Group", "capacity": 8, "student_ids": [student["id"]]}).json()["group"]["id"]
    plan = client.post("/subscription-plans", headers=headers, json={
        "name": "4 заняття", "price_minor": 100000, "period_days": 30, "lessons_included": 4,
        "usage_mode": "attendance", "absent_rule": "choice", "excused_rule": "makeup",
        "late_rule": "consume", "end_rule": "whichever_first", "renewal_trigger": "last_lesson", "allow_debt": True,
    }).json()
    charge = client.post("/billing/charges", headers=headers, json={
        "student_id": student["id"], "plan_id": plan["id"], "group_id": group_id,
        "starts_on": "2026-10-01", "due_date": "2026-10-01", "auto_renew": True,
    })
    assert charge.status_code == 201, charge.text

    lesson1 = client.post("/lesson-sessions", headers=headers, json={"group_id": group_id, "starts_at": "2026-10-05T17:00:00+03:00"}).json()
    assert client.put(f"/lesson-sessions/{lesson1['id']}/attendance", headers=headers, json={"items": [{"student_id": student["id"], "status": "present"}]}).status_code == 200
    subs = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    assert subs[0]["used_lessons"] == 1 and subs[0]["remaining_lessons"] == 3

    assert client.put(f"/lesson-sessions/{lesson1['id']}/attendance", headers=headers, json={"items": [{"student_id": student["id"], "status": "excused"}]}).status_code == 200
    subs = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    assert subs[0]["used_lessons"] == 0 and subs[0]["remaining_lessons"] == 4

    lesson2 = client.post("/lesson-sessions", headers=headers, json={"group_id": group_id, "starts_at": "2026-10-07T17:00:00+03:00"}).json()
    assert client.put(f"/lesson-sessions/{lesson2['id']}/attendance", headers=headers, json={"items": [{"student_id": student["id"], "status": "late"}]}).status_code == 200
    subs = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    # The next attendance uses the pending makeup first, so it does not spend
    # a new subscription lesson.
    assert subs[0]["used_lessons"] == 0 and subs[0]["remaining_lessons"] == 4

    lesson3 = client.post("/lesson-sessions", headers=headers, json={"group_id": group_id, "starts_at": "2026-10-09T17:00:00+03:00"}).json()
    assert client.put(f"/lesson-sessions/{lesson3['id']}/attendance", headers=headers, json={"items": [{"student_id": student["id"], "status": "absent", "consume_lesson": True}]}).status_code == 200
    subs = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    assert subs[0]["used_lessons"] == 1 and subs[0]["remaining_lessons"] == 3


def test_student_attendance_history_endpoint(client):
    org = create_org(client, "Attendance History", "attendance-history")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Іван", "age_at_inquiry": 10}).json()
    group = client.post("/groups", headers=headers, json={"name": "History Group", "capacity": 8}).json()
    enrollment = client.post("/enrollments", headers=headers, json={"student_id": student["id"], "group_id": group["id"]})
    assert enrollment.status_code == 201, enrollment.text
    lesson = client.post("/lesson-sessions", headers=headers, json={
        "group_id": group["id"], "starts_at": "2026-10-03T17:00:00+03:00", "topic": "FPV basics"
    }).json()
    marked = client.put(f"/lesson-sessions/{lesson['id']}/attendance", headers=headers, json={
        "items": [{"student_id": student["id"], "status": "late", "note": "10 хв"}]
    })
    assert marked.status_code == 200, marked.text

    history = client.get(f"/students/{student['id']}/attendance-history", headers=headers)
    assert history.status_code == 200, history.text
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["session_id"] == lesson["id"]
    assert rows[0]["group_name"] == "History Group"
    assert rows[0]["topic"] == "FPV basics"
    assert rows[0]["status"] == "late"
    assert rows[0]["note"] == "10 хв"


def test_tariff_requires_days_or_visits_and_can_be_archived(client):
    org = create_org(client, "Tariff Rules", "tariff-rules")
    headers = {"X-Organization-Id": org["id"]}

    invalid = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Empty limits", "price_minor": 100000, "period_days": None, "lessons_included": None},
    )
    assert invalid.status_code == 422, invalid.text

    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "8 / 30", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    )
    assert plan.status_code == 201, plan.text

    updated = client.put(
        f"/subscription-plans/{plan.json()['id']}",
        headers=headers,
        json={"name": "8 / 30", "price_minor": 220000, "period_days": 30, "lessons_included": 8, "is_active": False},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["price_minor"] == 220000
    assert updated.json()["is_active"] is False

    plans = client.get("/subscription-plans", headers=headers)
    assert plans.status_code == 200, plans.text
    archived = next(item for item in plans.json() if item["id"] == plan.json()["id"])
    assert archived["is_active"] is False

    events = client.get(
        "/audit-events",
        headers=headers,
        params={"entity_type": "subscription_plan", "entity_id": plan.json()["id"]},
    )
    assert events.status_code == 200, events.text
    changed = next(item for item in events.json() if item["event_type"] == "subscription_plan.updated")
    assert set(changed["payload"]["changed_fields"]) >= {"price_minor", "is_active"}


def test_existing_subscription_keeps_tariff_snapshot_after_template_edit(client):
    org = create_org(client, "Tariff Snapshot", "tariff-snapshot")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Марко"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Standard", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    ).json()

    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={"student_id": student["id"], "plan_id": plan["id"], "starts_on": date.today().isoformat()},
    )
    assert charge.status_code == 201, charge.text
    current = charge.json()["subscription"]
    assert current["price_minor"] == 200000
    assert current["period_days"] == 30
    assert current["lessons_included"] == 8
    assert current["lesson_unit_price_minor"] == 25000

    edited = client.put(
        f"/subscription-plans/{plan['id']}",
        headers=headers,
        json={"name": "Standard", "price_minor": 220000, "period_days": 31, "lessons_included": 10, "is_active": True},
    )
    assert edited.status_code == 200, edited.text

    refreshed = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers)
    assert refreshed.status_code == 200, refreshed.text
    row = refreshed.json()[0]
    assert row["price_minor"] == 200000
    assert row["period_days"] == 30
    assert row["lessons_included"] == 8
    assert row["lesson_unit_price_minor"] == 25000


def test_subscription_starts_from_first_planned_lesson(client):
    org = create_org(client, "First Lesson Start", "first-lesson-start")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Іван"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    group = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Start Group", "capacity": 8, "student_ids": [student["id"]]},
    ).json()["group"]
    first_date = date.today() + timedelta(days=3)
    lesson = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group["id"], "starts_at": first_date.isoformat() + "T17:00:00+03:00"},
    )
    assert lesson.status_code == 201, lesson.text
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Monthly", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    ).json()

    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan["id"],
            "group_id": group["id"],
            "starts_on": date.today().isoformat(),
        },
    )
    assert charge.status_code == 201, charge.text
    assert charge.json()["subscription"]["starts_on"] == first_date.isoformat()
    assert charge.json()["subscription"]["ends_on"] == (first_date + timedelta(days=29)).isoformat()


def test_change_tariff_now_keeps_used_lesson_price_and_creates_credit(client):
    org = create_org(client, "Immediate Tariff Credit", "immediate-tariff-credit")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Матвій"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    group_id = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Tariff Group", "capacity": 8, "student_ids": [student["id"]]},
    ).json()["group"]["id"]
    old_plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "2400", "price_minor": 240000, "period_days": 30, "lessons_included": 8},
    ).json()
    new_plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "2000", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    ).json()

    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": old_plan["id"],
            "group_id": group_id,
            "starts_on": "2026-10-01",
            "auto_renew": True,
        },
    )
    assert charge.status_code == 201, charge.text
    subscription_id = charge.json()["subscription"]["id"]
    payment_id = charge.json()["payment"]["id"]

    paid = client.patch(f"/payments/{payment_id}/paid", headers=headers, json={"method": "card"})
    assert paid.status_code == 200, paid.text

    first = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group_id, "starts_at": "2026-10-05T17:00:00+03:00"},
    ).json()
    marked = client.put(
        f"/lesson-sessions/{first['id']}/attendance",
        headers=headers,
        json={"items": [{"student_id": student["id"], "status": "present"}]},
    )
    assert marked.status_code == 200, marked.text

    changed = client.post(
        f"/student-subscriptions/{subscription_id}/change-plan",
        headers=headers,
        json={"plan_id": new_plan["id"], "reason": "Зміна умов поточного періоду"},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["used_lessons"] == 1
    assert body["old_unit_price_minor"] == 30000
    assert body["new_unit_price_minor"] == 25000
    assert body["current_period_charge_minor"] == 205000
    assert body["credit_minor"] == 35000
    assert body["debt_minor"] == 0
    assert body["subscription"]["plan_id"] == new_plan["id"]
    assert body["payment"]["adjusted_amount_minor"] == 205000
    assert body["payment"]["paid_minor"] == 240000
    assert body["payment"]["credit_minor"] == 35000

    # Seven remaining lessons are charged at the new unit price. On the last
    # one, auto-renewal applies the 350 UAH credit to the next 2000 UAH period.
    for day in [7, 9, 11, 13, 15, 17, 19]:
        lesson = client.post(
            "/lesson-sessions",
            headers=headers,
            json={"group_id": group_id, "starts_at": f"2026-10-{day:02d}T17:00:00+03:00"},
        ).json()
        response = client.put(
            f"/lesson-sessions/{lesson['id']}/attendance",
            headers=headers,
            json={"items": [{"student_id": student["id"], "status": "present"}]},
        )
        assert response.status_code == 200, response.text

    subscriptions = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    assert len(subscriptions) == 2
    next_subscription = subscriptions[0]
    assert next_subscription["renewal_of_id"] == subscription_id
    assert next_subscription["price_minor"] == 200000

    payments = client.get(f"/payments?student_id={student['id']}", headers=headers).json()
    next_payment = next(item for item in payments if item["subscription_id"] == next_subscription["id"])
    assert next_payment["amount_minor"] == 165000
    assert next_payment["balance_minor"] == 165000


def test_change_tariff_now_can_create_debt(client):
    org = create_org(client, "Immediate Tariff Debt", "immediate-tariff-debt")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олег"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    group_id = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Debt Group", "capacity": 8, "student_ids": [student["id"]]},
    ).json()["group"]["id"]
    old_plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "2000 Debt", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    ).json()
    new_plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "2400 Debt", "price_minor": 240000, "period_days": 30, "lessons_included": 8},
    ).json()
    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={"student_id": student["id"], "plan_id": old_plan["id"], "group_id": group_id, "starts_on": "2026-10-01"},
    ).json()
    client.patch(f"/payments/{charge['payment']['id']}/paid", headers=headers, json={"method": "card"})
    lesson = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group_id, "starts_at": "2026-10-05T17:00:00+03:00"},
    ).json()
    client.put(
        f"/lesson-sessions/{lesson['id']}/attendance",
        headers=headers,
        json={"items": [{"student_id": student["id"], "status": "present"}]},
    )

    changed = client.post(
        f"/student-subscriptions/{charge['subscription']['id']}/change-plan",
        headers=headers,
        json={"plan_id": new_plan["id"], "reason": "Зміна вартості"},
    )
    assert changed.status_code == 200, changed.text
    body = changed.json()
    assert body["current_period_charge_minor"] == 235000
    assert body["credit_minor"] == 0
    assert body["debt_minor"] == 35000
    assert body["payment"]["balance_minor"] == 35000


def test_excused_makeup_can_be_used_after_subscription_end(client):
    org = create_org(client, "Makeup After End", "makeup-after-end")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Софія"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    group_id = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Makeup Group", "capacity": 8, "student_ids": [student["id"]]},
    ).json()["group"]["id"]
    start = date.today()
    first = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group_id, "starts_at": start.isoformat() + "T17:00:00+03:00"},
    ).json()
    second_date = start + timedelta(days=1)
    second = client.post(
        "/lesson-sessions",
        headers=headers,
        json={"group_id": group_id, "starts_at": second_date.isoformat() + "T17:00:00+03:00"},
    ).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={
            "name": "1 day makeup", "price_minor": 100000, "period_days": 1, "lessons_included": 2,
            "excused_rule": "makeup",
        },
    ).json()
    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={"student_id": student["id"], "plan_id": plan["id"], "group_id": group_id, "starts_on": start.isoformat()},
    )
    assert charge.status_code == 201, charge.text

    excused = client.put(
        f"/lesson-sessions/{first['id']}/attendance",
        headers=headers,
        json={"items": [{"student_id": student["id"], "status": "excused"}]},
    )
    assert excused.status_code == 200, excused.text

    makeup = client.put(
        f"/lesson-sessions/{second['id']}/attendance",
        headers=headers,
        json={"items": [{"student_id": student["id"], "status": "present"}]},
    )
    assert makeup.status_code == 200, makeup.text

    subscription = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()[0]
    assert subscription["used_lessons"] == 0
    assert subscription["remaining_lessons"] == 2


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
    student_a = client.post("/students", headers=a_headers, json={"first_name": "Анна"}).json()
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

    student_a = client.post("/students", headers=a_headers, json={"first_name": "Anna"}).json()
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

    student_b = client.post("/students", headers=b_headers, json={"first_name": "Bohdan"}).json()
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


def test_teacher_has_admin_level_operational_access(client):
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
    created = client.post(
        "/staff",
        headers=teacher_headers,
        json={"full_name": "Second Teacher", "role": "teacher"},
    )
    assert created.status_code == 201, created.text

    plans = client.get("/subscription-plans", headers=teacher_headers)
    assert plans.status_code == 200, plans.text

    report = client.get("/reports/overview", headers=teacher_headers)
    assert report.status_code == 200, report.text

    owner_invite = client.post(
        "/organization-invitations",
        headers=teacher_headers,
        json={"email": "escalation@example.com", "role": "owner"},
    )
    assert owner_invite.status_code == 403


def test_admin_can_teach_when_responsibility_is_enabled(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKids",
            "organization_slug": "admin-teaches",
            "full_name": "Owner",
            "email": "owner-admin-teaches@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }

    group = client.post(
        "/groups/form",
        headers=owner_headers,
        json={"name": "FPV Admin Group", "capacity": 6, "location_id": None, "student_ids": [], "schedule_slots": []},
    )
    assert group.status_code == 201, group.text

    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "teaching-admin@example.com", "role": "admin", "can_teach": True},
    )
    assert invite.status_code == 201, invite.text
    assert invite.json()["can_teach"] is True

    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Teaching Admin",
            "password": "admin-secure-password",
        },
    )
    assert accepted.status_code == 200, accepted.text

    staff = client.get("/staff", headers=owner_headers)
    assert staff.status_code == 200, staff.text
    admin = next(item for item in staff.json() if item["email"] == "teaching-admin@example.com")
    assert admin["role"] == "admin"
    assert admin["can_teach"] is True

    assigned = client.post(
        f"/staff/{admin['id']}/groups",
        headers=owner_headers,
        json={"group_id": group.json()["group"]["id"], "is_primary": True},
    )
    assert assigned.status_code == 201, assigned.text


def test_non_teaching_staff_cannot_be_assigned_as_teacher(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKids",
            "organization_slug": "non-teaching-staff",
            "full_name": "Owner",
            "email": "owner-nonteaching@example.com",
            "password": "very-secure-password",
        },
    )
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": bootstrap.json()["organization_id"],
    }
    group = client.post(
        "/groups/form",
        headers=owner_headers,
        json={"name": "Manager Group", "capacity": 6, "location_id": None, "student_ids": [], "schedule_slots": []},
    ).json()
    manager = client.post(
        "/staff",
        headers=owner_headers,
        json={"full_name": "Office Manager", "role": "manager", "can_teach": False},
    )
    assert manager.status_code == 201, manager.text
    assert manager.json()["can_teach"] is False

    denied = client.post(
        f"/staff/{manager.json()['id']}/groups",
        headers=owner_headers,
        json={"group_id": group["group"]["id"], "is_primary": True},
    )
    assert denied.status_code == 409, denied.text


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
    second_invite = client.post(
        "/organization-invitations",
        headers=headers,
        json={"email": "single-teacher@example.com", "role": "teacher"},
    ).json()

    status_before = client.post(
        "/auth/invite-status",
        json={"invite_token": invite["invite_token"]},
    )
    assert status_before.status_code == 200
    assert status_before.json() == {"status": "valid"}

    payload = {
        "invite_token": invite["invite_token"],
        "full_name": "Teacher",
        "password": "teacher-secure-password",
    }
    assert client.post("/auth/accept-invite", json=payload).status_code == 200

    status_after = client.post(
        "/auth/invite-status",
        json={"invite_token": invite["invite_token"]},
    )
    assert status_after.status_code == 200
    assert status_after.json() == {"status": "accepted"}

    second_status = client.post(
        "/auth/invite-status",
        json={"invite_token": second_invite["invite_token"]},
    )
    assert second_status.status_code == 200
    assert second_status.json() == {"status": "accepted"}

    reused = client.post("/auth/accept-invite", json=payload)
    assert reused.status_code == 409
    assert reused.json()["detail"] == "This invitation has already been accepted"


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


def test_teacher_workspace_and_lessons_have_full_operational_access(client):
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
    assert {item["name"] for item in groups.json()} == {"Teacher Group"}

    workspace_students = client.get("/workspace/students", headers=teacher_headers)
    assert workspace_students.status_code == 200, workspace_students.text
    assert {item["first_name"] for item in workspace_students.json()} == {"Assigned Child"}

    # A teacher may work only with explicitly assigned groups/students.
    assert client.get("/workspace/leads", headers=teacher_headers).status_code == 403
    assert client.get(f"/groups/{group_a_id}/roster", headers=teacher_headers).status_code == 200
    assert client.get(f"/groups/{group_b_id}/roster", headers=teacher_headers).status_code == 403

    allowed_session = client.post(
        "/lesson-sessions",
        headers=teacher_headers,
        json={"group_id": group_a_id, "starts_at": "2026-10-10T17:00:00+03:00"},
    )
    assert allowed_session.status_code == 201, allowed_session.text

    second_session = client.post(
        "/lesson-sessions",
        headers=teacher_headers,
        json={"group_id": group_b_id, "starts_at": "2026-10-10T18:00:00+03:00"},
    )
    assert second_session.status_code == 403, second_session.text


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


def test_manual_intake_normalizes_phone_source_aliases(client):
    org = create_org(client, "AeroKiDS", "manual-source-normalization")
    headers = {"X-Organization-Id": org["id"]}

    cases = (("phone", "Марко"), ("Phone", "Іван"), ("iPhone", "Олег"), ("Телефон", "Назар"))
    for index, (raw_source, child_name) in enumerate(cases, start=1):
        response = client.post(
            "/intake",
            headers=headers,
            json={
                "child_first_name": child_name,
                "child_age": 9 + index,
                "contact_name": "Оксана Петренко",
                "phone": f"06722233{40 + index}",
                "source": raw_source,
            },
        )
        assert response.status_code == 201, response.text

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert {item["source"] for item in leads.json()} == {"phone"}


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


def test_lead_details_can_be_edited_including_comment_and_contact(client):
    org = create_org(client, "Editable Leads", "editable-leads")
    headers = {"X-Organization-Id": org["id"]}

    created = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Софія",
            "child_age": 10,
            "contact_name": "Марина Коваль",
            "phone": "0672223344",
            "source": "phone",
            "comment": "Початковий коментар",
        },
    )
    assert created.status_code == 201, created.text
    student_id = created.json()["student_id"]

    updated = client.patch(
        f"/students/{student_id}/lead-details",
        headers=headers,
        json={
            "child_first_name": "Софія",
            "child_last_name": "Іваненко",
            "child_phone": "093 111 22 33",
            "child_age": 11,
            "contact_name": "Марина Іваненко",
            "phone": "050 222 33 44",
            "source": "instagram",
            "comment": "Хочуть FPV, зручно після 17:00",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["first_name"] == "Софія"
    assert updated.json()["last_name"] == "Іваненко"
    assert updated.json()["phone"] == "+380931112233"
    assert updated.json()["age_at_inquiry"] == 11
    assert updated.json()["source"] == "instagram"
    assert updated.json()["notes"] == "Хочуть FPV, зручно після 17:00"

    detail = client.get(f"/students/{student_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["contacts"][0]["full_name"] == "Марина Іваненко"
    assert detail.json()["contacts"][0]["phone"] == "+380502223344"

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    row = next(item for item in leads.json() if item["student_id"] == student_id)
    assert row["last_name"] == "Іваненко"
    assert row["student_phone"] == "+380931112233"
    assert row["contact_name"] == "Марина Іваненко"
    assert row["contact_phone"] == "+380502223344"
    assert row["comment"] == "Хочуть FPV, зручно після 17:00"

    events = client.get(
        "/audit-events",
        headers=headers,
        params={"entity_type": "student", "entity_id": student_id},
    )
    assert events.status_code == 200, events.text
    edited = next(item for item in events.json() if item["event_type"] == "lead.details_updated")
    assert "comment" in edited["payload"]["changed_fields"]
    assert edited["payload"]["comment_changed"] is True


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


def test_first_intake_accepts_missing_surnames_from_site_and_manual_entry(client):
    org = create_org(client, "Partial Names", "partial-names")
    headers = {"X-Organization-Id": org["id"]}

    website = client.post(
        "/public/intake/partial-names",
        json={
            "child_first_name": "Марко",
            "child_age": 9,
            "contact_name": "Оксана",
            "phone": "0671112233",
            "source": "website",
        },
    )
    assert website.status_code == 201, website.text

    manual = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Софія",
            "child_age": 10,
            "contact_name": "Марина",
            "phone": "0502223344",
            "source": "phone",
        },
    )
    assert manual.status_code == 201, manual.text

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    rows = {item["first_name"]: item for item in leads.json()}

    assert rows["Марко"]["last_name"] is None
    assert rows["Марко"]["contact_name"] == "Оксана"
    assert rows["Софія"]["last_name"] is None
    assert rows["Софія"]["contact_name"] == "Марина"


def test_intake_normalizes_ukrainian_phone_and_deduplicates_repeat(client):
    org = create_org(client, "International School", "international-intake")

    first = client.post(
        "/public/intake/international-intake",
        json={
            "child_first_name": "Ola",
            "child_age": 9,
            "contact_name": "Anna",
            "phone": "067 123 45 67",
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
            "phone": "+380 (67) 123-45-67",
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
    assert leads.json()[0]["contact_phone"] == "+380671234567"

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


def test_repeat_website_intake_keeps_student_and_appends_comment(client):
    org = create_org(client, "Repeat Website", "repeat-website")
    headers = {"X-Organization-Id": org["id"]}
    first = client.post(
        "/public/intake/repeat-website",
        json={
            "child_first_name": "Максим",
            "child_age": 10,
            "contact_name": "Оксана Петренко",
            "phone": "0671234567",
            "source": "website",
            "comment": "Перше звернення",
        },
    )
    assert first.status_code == 201, first.text

    repeated = client.post(
        "/public/intake/repeat-website",
        json={
            "child_first_name": "Максим",
            "child_age": 10,
            "contact_name": "Оксана Петренко",
            "phone": "+380 67 123 45 67",
            "source": "website",
            "comment": "Хочемо записатися ще раз",
        },
    )
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["student_id"] == first.json()["student_id"]

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert len(leads.json()) == 1
    comment = leads.json()[0]["comment"]
    assert "Перше звернення" in comment
    assert "Повторне звернення через сайт" in comment
    assert "Хочемо записатися ще раз" in comment


def test_manual_intake_blocks_same_child_but_allows_sibling_same_parent_phone(client):
    org = create_org(client, "Duplicate Phone", "duplicate-phone")
    headers = {"X-Organization-Id": org["id"]}
    original = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Марко",
            "child_age": 9,
            "contact_name": "Олена Коваль",
            "phone": "0675554433",
            "source": "phone",
        },
    )
    assert original.status_code == 201, original.text
    student_id = original.json()["student_id"]

    duplicate_check = client.post(
        "/intake/duplicate-check",
        headers=headers,
        json={
            "child_first_name": "Марко",
            "child_age": 9,
            "phone": "+380675554433",
        },
    )
    assert duplicate_check.status_code == 200, duplicate_check.text
    assert duplicate_check.json()["matches"][0]["student_id"] == student_id
    assert duplicate_check.json()["matches"][0]["likely_same_student"] is True

    blocked = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Марко",
            "child_age": 9,
            "contact_name": "Олена Коваль",
            "phone": "0675554433",
            "source": "phone",
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["detail"]["code"] == "duplicate_phone"
    assert blocked.json()["detail"]["student_id"] == student_id

    sibling_check = client.post(
        "/intake/duplicate-check",
        headers=headers,
        json={
            "child_first_name": "Софія",
            "child_age": 11,
            "phone": "0675554433",
        },
    )
    assert sibling_check.status_code == 200, sibling_check.text
    assert sibling_check.json()["matches"]
    assert all(item["likely_same_student"] is False for item in sibling_check.json()["matches"])

    sibling = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Софія",
            "child_age": 11,
            "contact_name": "Олена Коваль",
            "phone": "0675554433",
            "source": "phone",
        },
    )
    assert sibling.status_code == 201, sibling.text
    assert sibling.json()["student_id"] != student_id


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


def test_subscription_charge_defaults_due_date_to_start_date(client):
    org = create_org(client, "Due Date Billing", "due-date-billing")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Ніна"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Monthly due", "price_minor": 100000, "period_days": 30},
    ).json()
    response = client.post(
        "/billing/charges",
        headers=headers,
        json={"student_id": student["id"], "plan_id": plan["id"], "starts_on": "2026-10-15"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["payment"]["due_date"] == "2026-10-15"


def test_paid_payment_cannot_be_marked_paid_twice(client):
    org = create_org(client, "Paid Once", "paid-once")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Роман"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 50000, "due_date": "2026-10-01"},
    ).json()
    first = client.patch(
        f"/payments/{payment['id']}/paid",
        headers=headers,
        json={"method": "cash"},
    )
    second = client.patch(
        f"/payments/{payment['id']}/paid",
        headers=headers,
        json={"method": "card"},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 409, second.text


def test_partial_payment_tracks_balance_and_full_settlement(client):
    org = create_org(client, "Partial Pay", "partial-pay")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Тарас"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 180000, "due_date": "2000-01-01"},
    ).json()

    partial = client.post(
        f"/payments/{payment['id']}/receipts",
        headers=headers,
        json={"amount_minor": 80000, "method": "cash", "note": "Перша частина"},
    )
    assert partial.status_code == 201, partial.text
    assert partial.json()["status"] == "pending"
    assert partial.json()["paid_minor"] == 80000
    assert partial.json()["balance_minor"] == 100000

    full = client.patch(
        f"/payments/{payment['id']}/paid",
        headers=headers,
        json={"method": "card"},
    )
    assert full.status_code == 200, full.text
    assert full.json()["status"] == "paid"
    assert full.json()["paid_minor"] == 180000
    assert full.json()["balance_minor"] == 0

    tx = client.get(f"/payments/{payment['id']}/transactions", headers=headers)
    assert tx.status_code == 200
    assert [item["amount_minor"] for item in tx.json()] == [80000, 100000]


def test_refund_with_charge_reduction_preserves_zero_balance(client):
    org = create_org(client, "Refund Pay", "refund-pay")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Леся"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 100000},
    ).json()
    client.patch(f"/payments/{payment['id']}/paid", headers=headers, json={"method": "bank"})

    refund = client.post(
        f"/payments/{payment['id']}/refunds",
        headers=headers,
        json={"amount_minor": 30000, "note": "Перерахунок за пропущені заняття", "reduce_charge": True},
    )
    assert refund.status_code == 201, refund.text
    body = refund.json()
    assert body["paid_minor"] == 100000
    assert body["refunded_minor"] == 30000
    assert body["adjusted_amount_minor"] == 70000
    assert body["balance_minor"] == 0
    assert body["status"] == "paid"


def test_payment_adjustment_changes_only_effective_charge(client):
    org = create_org(client, "Adjust Pay", "adjust-pay")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Ігор"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 120000},
    ).json()

    adjusted = client.post(
        f"/payments/{payment['id']}/adjustments",
        headers=headers,
        json={"direction": "decrease", "amount_minor": 20000, "reason": "Разова знижка"},
    )
    assert adjusted.status_code == 201, adjusted.text
    assert adjusted.json()["amount_minor"] == 120000
    assert adjusted.json()["adjusted_amount_minor"] == 100000
    assert adjusted.json()["balance_minor"] == 100000


def test_subscription_pause_resume_extends_period(client):
    org = create_org(client, "Pause Sub", "pause-sub")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Оля"}).json()
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "30 days", "price_minor": 100000, "period_days": 30},
    ).json()
    start = date.today() - timedelta(days=10)
    subscription = client.post(
        "/student-subscriptions",
        headers=headers,
        json={"student_id": student["id"], "plan_id": plan["id"], "starts_on": start.isoformat()},
    ).json()
    old_end = date.fromisoformat(subscription["ends_on"])

    pause_start = date.today() - timedelta(days=5)
    resume_on = date.today() - timedelta(days=2)
    paused = client.post(
        f"/student-subscriptions/{subscription['id']}/pause",
        headers=headers,
        json={"starts_on": pause_start.isoformat(), "resume_on": resume_on.isoformat(), "note": "Канікули"},
    )
    assert paused.status_code == 201, paused.text

    run = client.post("/billing/renewals/run", headers=headers, json={"through_date": (date.today() + timedelta(days=1)).isoformat()})
    assert run.status_code == 200, run.text
    assert run.json()["resumed_subscriptions"] == 1

    refreshed = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()[0]
    paused_days = (resume_on - pause_start).days
    assert date.fromisoformat(refreshed["ends_on"]) == old_end + timedelta(days=paused_days)
    assert refreshed["status"] == "active"


def test_auto_renewal_is_idempotent_and_requires_active_enrollment(client):
    org = create_org(client, "Renew Sub", "renew-sub")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Марта"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    client.post("/groups/form", headers=headers, json={"name": "Renew Group", "capacity": 8, "student_ids": [student["id"]]})

    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Monthly renew", "price_minor": 180000, "period_days": 30},
    ).json()
    start = date.today() - timedelta(days=29)
    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan["id"],
            "starts_on": start.isoformat(),
            "auto_renew": True,
        },
    )
    assert charge.status_code == 201, charge.text

    horizon = (date.today() + timedelta(days=7)).isoformat()
    first = client.post("/billing/renewals/run", headers=headers, json={"through_date": horizon})
    second = client.post("/billing/renewals/run", headers=headers, json={"through_date": horizon})
    assert first.status_code == 200, first.text
    assert first.json()["created_subscriptions"] == 1
    assert second.status_code == 200, second.text
    assert second.json()["created_subscriptions"] == 0

    subscriptions = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    payments = client.get(f"/payments?student_id={student['id']}", headers=headers).json()
    assert len(subscriptions) == 2
    assert len(payments) == 2
    assert subscriptions[0]["renewal_of_id"] == subscriptions[1]["id"]
    assert subscriptions[0]["discount_minor"] == 0
    assert subscriptions[1]["status"] == "active"


def test_auto_renewal_skips_stale_subscription_instead_of_backfilling(client):
    org = create_org(client, "Stale Renew", "stale-renew")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Назар"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    client.post("/groups/form", headers=headers, json={"name": "Stale Group", "capacity": 8, "student_ids": [student["id"]]})
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Stale Monthly", "price_minor": 150000, "period_days": 30},
    ).json()
    old_start = date.today() - timedelta(days=100)
    client.post(
        "/billing/charges",
        headers=headers,
        json={"student_id": student["id"], "plan_id": plan["id"], "starts_on": old_start.isoformat(), "auto_renew": True},
    )

    result = client.post(
        "/billing/renewals/run",
        headers=headers,
        json={"through_date": (date.today() + timedelta(days=7)).isoformat()},
    )
    assert result.status_code == 200, result.text
    assert result.json()["created_subscriptions"] == 0
    assert result.json()["skipped_stale_subscriptions"] == 1


def test_legacy_paid_charge_can_be_refunded_without_losing_settlement(client):
    org = create_org(client, "Legacy Refund", "legacy-refund")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Legacy"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 100000},
    ).json()
    paid = client.patch(
        f"/payments/{payment['id']}/paid",
        headers=headers,
        json={"method": "card"},
    )
    assert paid.status_code == 200, paid.text

    refund = client.post(
        f"/payments/{payment['id']}/refunds",
        headers=headers,
        json={"amount_minor": 20000, "note": "Часткове повернення", "reduce_charge": True},
    )
    assert refund.status_code == 201, refund.text
    body = refund.json()
    assert body["paid_minor"] == 100000
    assert body["refunded_minor"] == 20000
    assert body["adjusted_amount_minor"] == 80000
    assert body["balance_minor"] == 0


def test_adjustment_cannot_create_hidden_overpayment(client):
    org = create_org(client, "Adjust Guard", "adjust-guard")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Guard"}).json()
    payment = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 100000},
    ).json()
    partial = client.post(
        f"/payments/{payment['id']}/receipts",
        headers=headers,
        json={"amount_minor": 80000, "method": "cash"},
    )
    assert partial.status_code == 201

    invalid = client.post(
        f"/payments/{payment['id']}/adjustments",
        headers=headers,
        json={"direction": "decrease", "amount_minor": 30000, "reason": "Too much"},
    )
    assert invalid.status_code == 422


def test_auto_renewal_handles_recently_expired_period(client):
    org = create_org(client, "Recent Expired Renew", "recent-expired-renew")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Святослав"}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    client.post("/groups/form", headers=headers, json={"name": "Recent Renew Group", "capacity": 8, "student_ids": [student["id"]]})
    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Recent Monthly", "price_minor": 140000, "period_days": 30},
    ).json()
    start = date.today() - timedelta(days=31)
    charge = client.post(
        "/billing/charges",
        headers=headers,
        json={
            "student_id": student["id"],
            "plan_id": plan["id"],
            "starts_on": start.isoformat(),
            "auto_renew": True,
        },
    )
    assert charge.status_code == 201, charge.text

    result = client.post(
        "/billing/renewals/run",
        headers=headers,
        json={"through_date": (date.today() + timedelta(days=7)).isoformat()},
    )
    assert result.status_code == 200, result.text
    assert result.json()["created_subscriptions"] == 1

    subscriptions = client.get(f"/student-subscriptions?student_id={student['id']}", headers=headers).json()
    assert len(subscriptions) == 2
    assert subscriptions[1]["status"] == "expired"
    assert subscriptions[0]["renewal_of_id"] == subscriptions[1]["id"]


def test_ukrainian_phone_formats_normalize_to_one_contact(client):
    org = create_org(client, "Phone Validation", "phone-validation")
    headers = {"X-Organization-Id": org["id"]}

    first = client.post(
        "/contacts",
        headers=headers,
        json={"full_name": "Оксана Петренко", "phone": "067 123 45 67"},
    )
    assert first.status_code == 201, first.text
    assert first.json()["phone"] == "+380671234567"

    second = client.post(
        "/contacts",
        headers=headers,
        json={"full_name": "Оксана Петренко", "phone": "+380 (67) 123-45-67"},
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]


def test_invalid_ukrainian_phone_is_rejected(client):
    org = create_org(client, "Bad Phone", "bad-phone")
    headers = {"X-Organization-Id": org["id"]}

    for phone in ["12345", "+48123123123", "0012345678", "+380001234567"]:
        response = client.post(
            "/contacts",
            headers=headers,
            json={"full_name": "Ірина Тест", "phone": phone},
        )
        assert response.status_code == 422, (phone, response.text)


def test_person_names_reject_digits_and_noise(client):
    org = create_org(client, "Name Validation", "name-validation")
    headers = {"X-Organization-Id": org["id"]}

    bad_contact = client.post(
        "/contacts",
        headers=headers,
        json={"full_name": "Оксана123", "phone": "0671234567"},
    )
    assert bad_contact.status_code == 422

    bad_student = client.post(
        "/students",
        headers=headers,
        json={"first_name": "!!!"},
    )
    assert bad_student.status_code == 422

    good_student = client.post(
        "/students",
        headers=headers,
        json={"first_name": "  Марія   Анна  "},
    )
    assert good_student.status_code == 201, good_student.text
    assert good_student.json()["first_name"] == "Марія Анна"


def test_staff_identity_fields_are_validated_and_normalized(client):
    org = create_org(client, "Staff Validation", "staff-validation")
    headers = {"X-Organization-Id": org["id"]}

    bad_email = client.post(
        "/staff",
        headers=headers,
        json={"full_name": "Іван Петренко", "role": "teacher", "email": "wrong-email"},
    )
    assert bad_email.status_code == 422

    bad_phone = client.post(
        "/staff",
        headers=headers,
        json={"full_name": "Іван Петренко", "role": "teacher", "phone": "+12025550123"},
    )
    assert bad_phone.status_code == 422

    good = client.post(
        "/staff",
        headers=headers,
        json={
            "full_name": "  Іван   Петренко ",
            "role": "teacher",
            "email": "IVAN@EXAMPLE.COM ",
            "phone": "050 123 45 67",
        },
    )
    assert good.status_code == 201, good.text
    assert good.json()["full_name"] == "Іван Петренко"
    assert good.json()["email"] == "ivan@example.com"
    assert good.json()["phone"] == "+380501234567"


def test_intake_rejects_invalid_identity_before_creating_records(client):
    org = create_org(client, "Intake Validation", "intake-validation")
    headers = {"X-Organization-Id": org["id"]}

    invalid = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Максим7",
            "child_age": 9,
            "contact_name": "Оксана",
            "phone": "0671234567",
            "source": "phone",
        },
    )
    assert invalid.status_code == 422
    assert client.get("/students", headers=headers).json() == []
    assert client.get("/contacts", headers=headers).json() == []


def test_completed_trial_candidate_can_join_existing_group(client):
    org = create_org(client, "Existing Group Enroll", "existing-group-enroll")
    headers = {"X-Organization-Id": org["id"]}

    student = client.post(
        "/students",
        headers=headers,
        json={"first_name": "Марко", "age_at_inquiry": 10},
    ).json()
    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={
            "student_id": student["id"],
            "starts_at": "2026-10-02T15:00:00+03:00",
        },
    ).json()
    completed = client.patch(
        f"/trial-lessons/{trial['id']}/complete",
        headers=headers,
        json={"status": "completed", "recommended_level": "Початковий"},
    )
    assert completed.status_code == 200, completed.text

    group = client.post(
        "/groups",
        headers=headers,
        json={"name": "FPV Existing", "capacity": 6, "min_age": 9, "max_age": 12},
    ).json()
    schedule = client.post(
        "/group-schedules",
        headers=headers,
        json={"group_id": group["id"], "weekday": 2, "start_time": "17:00", "duration_minutes": 60},
    )
    assert schedule.status_code == 201, schedule.text

    enrolled = client.post(
        "/enrollments",
        headers=headers,
        json={"student_id": student["id"], "group_id": group["id"]},
    )
    assert enrolled.status_code == 201, enrolled.text
    body = enrolled.json()
    assert body["group_id"] == group["id"]
    assert body["student_id"] == student["id"]
    assert body["schedule_match"] in {"match", "partial", "conflict", "unknown"}
    assert body["schedule_note"]

    profile = client.get(f"/students/{student['id']}/profile", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["crm_status"] == "enrolled"
    assert profile.json()["student_status"] == "active"

    detail = client.get(f"/groups/{group['id']}/detail", headers=headers)
    assert detail.status_code == 200
    assert [member["student_id"] for member in detail.json()["members"]] == [student["id"]]


def test_student_can_be_active_without_group_or_location(client):
    org = create_org(client, "Independent Student", "independent-student")
    headers = {"X-Organization-Id": org["id"]}

    intake = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Ірина",
            "child_age": 12,
            "contact_name": "Олена Коваль",
            "phone": "0674443322",
            "source": "phone",
        },
    )
    assert intake.status_code == 201, intake.text
    student_id = intake.json()["student_id"]

    activated = client.post(f"/students/{student_id}/enroll-without-group", headers=headers, json={})
    assert activated.status_code == 200, activated.text
    assert activated.json()["crm_status"] == "enrolled"
    assert activated.json()["student_status"] == "active"

    students = client.get("/workspace/students", headers=headers)
    assert students.status_code == 200, students.text
    row = next(item for item in students.json() if item["student_id"] == student_id)
    assert row["group_id"] is None
    assert row["group_name"] is None

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    assert all(item["student_id"] != student_id for item in leads.json())

    group = client.post(
        "/groups/form",
        headers=headers,
        json={
            "name": "Online Later Group",
            "capacity": 6,
            "location_id": None,
            "student_ids": [],
            "schedule_slots": [],
        },
    )
    assert group.status_code == 201, group.text
    assert group.json()["group"]["location_id"] is None
    assert group.json()["enrolled_student_ids"] == []

    enrolled = client.post(
        "/enrollments",
        headers=headers,
        json={"student_id": student_id, "group_id": group.json()["group"]["id"]},
    )
    assert enrolled.status_code == 201, enrolled.text

    students_after = client.get("/workspace/students", headers=headers).json()
    row_after = next(item for item in students_after if item["student_id"] == student_id)
    assert row_after["group_id"] == group.json()["group"]["id"]


def test_candidate_without_completed_trial_can_join_existing_group(client):
    org = create_org(client, "Existing Group Direct", "existing-group-direct")
    headers = {"X-Organization-Id": org["id"]}
    student = client.post("/students", headers=headers, json={"first_name": "Олег"}).json()
    group = client.post("/groups", headers=headers, json={"name": "FPV Direct", "capacity": 6}).json()

    response = client.post(
        "/enrollments",
        headers=headers,
        json={"student_id": student["id"], "group_id": group["id"]},
    )
    assert response.status_code == 201, response.text
    detail = client.get(f"/students/{student['id']}", headers=headers).json()
    assert detail["crm_status"] == "enrolled"
    assert detail["student_status"] == "active"


def test_existing_group_enrollment_respects_capacity(client):
    org = create_org(client, "Existing Group Capacity", "existing-group-capacity")
    headers = {"X-Organization-Id": org["id"]}
    group = client.post("/groups", headers=headers, json={"name": "FPV One Seat", "capacity": 1}).json()

    student_ids = []
    for name in ["Анна", "Богдан"]:
        student = client.post("/students", headers=headers, json={"first_name": name}).json()
        trial = client.post(
            "/trial-lessons",
            headers=headers,
            json={"student_id": student["id"], "starts_at": "2026-10-02T16:00:00+03:00"},
        ).json()
        client.patch(
            f"/trial-lessons/{trial['id']}/complete",
            headers=headers,
            json={"status": "completed", "recommended_level": "Початковий"},
        )
        student_ids.append(student["id"])

    first = client.post("/enrollments", headers=headers, json={"student_id": student_ids[0], "group_id": group["id"]})
    second = client.post("/enrollments", headers=headers, json={"student_id": student_ids[1], "group_id": group["id"]})
    assert first.status_code == 201, first.text
    assert second.status_code == 409


def test_lesson_session_blocks_overlapping_time_for_same_group(client):
    org = create_org(client, "Lesson Collision", "lesson-collision")
    headers = {"X-Organization-Id": org["id"]}
    group = client.post("/groups", headers=headers, json={"name": "Collision Group", "capacity": 8}).json()

    first = client.post(
        "/lesson-sessions",
        headers=headers,
        json={
            "group_id": group["id"],
            "starts_at": "2026-10-06T12:00:00+03:00",
            "duration_minutes": 60,
            "topic": "Перше заняття",
        },
    )
    assert first.status_code == 201, first.text

    overlap = client.post(
        "/lesson-sessions",
        headers=headers,
        json={
            "group_id": group["id"],
            "starts_at": "2026-10-06T12:45:00+03:00",
            "duration_minutes": 60,
            "topic": "Перетин",
        },
    )
    assert overlap.status_code == 409, overlap.text
    assert "Час зайнятий" in overlap.json()["detail"]

    adjacent = client.post(
        "/lesson-sessions",
        headers=headers,
        json={
            "group_id": group["id"],
            "starts_at": "2026-10-06T13:00:00+03:00",
            "duration_minutes": 60,
            "topic": "Наступне заняття",
        },
    )
    assert adjacent.status_code == 201, adjacent.text


def test_child_phone_is_stored_separately_from_responsible_contact(client):
    org = create_org(client, "Child Contact", "child-contact")
    headers = {"X-Organization-Id": org["id"]}

    intake = client.post(
        "/intake",
        headers=headers,
        json={
            "child_first_name": "Максим",
            "child_last_name": "Коваль",
            "child_phone": "067 111 22 33",
            "child_age": 10,
            "contact_name": "Оксана Коваль",
            "phone": "050 222 33 44",
            "source": "phone",
        },
    )
    assert intake.status_code == 201, intake.text

    leads = client.get("/workspace/leads", headers=headers)
    assert leads.status_code == 200, leads.text
    row = leads.json()[0]
    assert row["first_name"] == "Максим"
    assert row["last_name"] == "Коваль"
    assert row["student_phone"] == "+380671112233"
    assert row["contact_name"] == "Оксана Коваль"
    assert row["contact_phone"] == "+380502223344"


def test_group_overview_exposes_assigned_teacher(client):
    org = create_org(client, "Group Teacher", "group-teacher")
    headers = {"X-Organization-Id": org["id"]}
    group = client.post("/groups", headers=headers, json={"name": "Teacher Group", "capacity": 8}).json()
    staff = client.post(
        "/staff",
        headers=headers,
        json={"full_name": "Іван Петренко", "role": "teacher"},
    )
    assert staff.status_code == 201, staff.text
    teacher = staff.json()

    assigned = client.post(
        f"/staff/{teacher['id']}/groups",
        headers=headers,
        json={"group_id": group["id"], "is_primary": True},
    )
    assert assigned.status_code == 201, assigned.text

    groups = client.get("/workspace/groups", headers=headers)
    assert groups.status_code == 200, groups.text
    row = next(item for item in groups.json() if item["group_id"] == group["id"])
    assert row["primary_teacher_id"] == teacher["id"]
    assert row["primary_teacher_name"] == "Іван Петренко"
