from uuid import UUID

from app.db.session import SessionLocal
from app.models.core import CrmStatus, Student, StudentStatus


def create_org(client, name, slug):
    response = client.post("/organizations", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()


def make_waiting_student(client, headers, name, start="17:00"):
    student = client.post("/students", headers=headers, json={"first_name": name, "age_at_inquiry": 10}).json()
    ready = client.patch(f"/students/{student['id']}/lead-outcome", headers=headers, json={"crm_status": "waiting_for_group"})
    assert ready.status_code == 200, ready.text
    saved = client.put(f"/students/{student['id']}/preferences", headers=headers, json={
        "preferred_location_id": None,
        "availability": [{"weekday": 1, "start_time": start, "end_time": "19:00", "preference": "preferred"}],
    })
    assert saved.status_code == 200, saved.text
    return student["id"]


def test_proposal_is_saved_and_tenant_scoped(client):
    org = create_org(client, "School A", "potential-group-a")
    other_org = create_org(client, "School B", "potential-group-b")
    headers = {"X-Organization-Id": org["id"]}
    other_headers = {"X-Organization-Id": other_org["id"]}
    first = make_waiting_student(client, headers, "Anna")
    second = make_waiting_student(client, headers, "Bohdan", "17:30")
    other_student = make_waiting_student(client, other_headers, "Other")
    shift = client.put(f"/students/{first}/preferences", headers=headers, json={
        "preferred_location_id": None,
        "school_shift": "first",
        "availability": [{"weekday": 1, "start_time": "17:00", "end_time": "19:00", "preference": "preferred"}],
    })
    assert shift.status_code == 200, shift.text
    assert shift.json()["school_shift"] == "first"
    proposal = {
        "members": [
            {"student_id": first, "response": "not_contacted", "availability_snapshot": [{"weekday": 1, "start_time": "17:00", "end_time": "19:00", "preference": "preferred"}]},
            {"student_id": second, "response": "awaiting", "availability_snapshot": [{"weekday": 1, "start_time": "17:30", "end_time": "19:00", "preference": "preferred"}]},
        ],
        "slots": [{"weekday": 1, "start_time": "17:30", "end_time": "18:30", "exact_match": True}],
        "selected_slots": [{"weekday": 1, "start_time": "17:30", "end_time": "18:30", "exact_match": True}, {"weekday": 3, "start_time": "17:30", "end_time": "18:30", "exact_match": True}],
        "stale": False,
    }
    created = client.post("/groups/potential-proposals", headers=headers, json=proposal)
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    assert created.json()["members"][1]["response"] == "awaiting"

    listed = client.get("/groups/potential-proposals", headers=headers)
    assert [item["id"] for item in listed.json()] == [proposal_id]
    assert client.get("/groups/potential-proposals", headers=other_headers).json() == []

    cross_tenant = {**proposal, "members": [proposal["members"][0], {**proposal["members"][1], "student_id": other_student}]}
    rejected = client.post("/groups/potential-proposals", headers=headers, json=cross_tenant)
    assert rejected.status_code == 422

    updated = {**proposal, "version": created.json()["version"], "members": [{**proposal["members"][0], "response": "agreed"}, proposal["members"][1]]}
    saved = client.put(f"/groups/potential-proposals/{proposal_id}", headers=headers, json=updated)
    assert saved.status_code == 200, saved.text
    assert saved.json()["members"][0]["response"] == "agreed"


def test_proposal_rejects_student_with_current_group_enrollment(client):
    org = create_org(client, "Enrolled Candidate School", "enrolled-candidate")
    headers = {"X-Organization-Id": org["id"]}
    enrolled_id = make_waiting_student(client, headers, "Already Enrolled")
    waiting_id = make_waiting_student(client, headers, "Still Waiting")
    group = client.post("/groups", headers=headers, json={"name": "Current Group", "capacity": 8}).json()
    enrollment = client.post("/enrollments", headers=headers, json={"student_id": enrolled_id, "group_id": group["id"]})
    assert enrollment.status_code == 201, enrollment.text

    # Cover stale funnel data: enrollment is current even if the lead status is wrong.
    with SessionLocal() as db:
        student = db.get(Student, UUID(enrolled_id))
        student.crm_status = CrmStatus.WAITING_FOR_GROUP
        student.student_status = StudentStatus.PROSPECT
        db.commit()

    payload = {
        "members": [{"student_id": student_id} for student_id in (enrolled_id, waiting_id)],
        "slots": [{"weekday": 1, "start_time": "17:00", "end_time": "18:00"}],
    }
    response = client.post("/groups/potential-proposals", headers=headers, json=payload)
    assert response.status_code == 422, response.text


def setup_proposal(client, slug="workflow"):
    org = create_org(client, "Proposal School", slug)
    headers = {"X-Organization-Id": org["id"]}
    ids = [make_waiting_student(client, headers, name) for name in ("Anna", "Bohdan")]
    availability = [{"weekday": 1, "start_time": "17:00", "end_time": "19:00", "preference": "preferred"}]
    slots = [{"weekday": day, "start_time": "17:00", "end_time": "18:00", "exact_match": True} for day in (1, 3)]
    payload = {"members": [{"student_id": sid, "response": "agreed", "availability_snapshot": availability} for sid in ids], "slots": slots, "selected_slots": slots}
    response = client.post("/groups/potential-proposals", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return headers, ids, response.json()


def test_schedule_change_requires_reconfirmation_and_rejects_stale_save(client):
    headers, ids, proposal = setup_proposal(client)
    changed = {**proposal, "selected_slots": [{**s, "start_time": "18:00", "end_time": "19:00"} for s in proposal["selected_slots"]]}
    response = client.put(f"/groups/potential-proposals/{proposal['id']}", headers=headers, json=changed)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert all(m["response"] == "reconfirm" for m in saved["members"])
    assert saved["schedule_history"][0]["responses"][0]["response"] == "agreed"
    assert saved["schedule_history"][0]["before"][0]["start_time"].startswith("17:00")
    assert client.put(f"/groups/potential-proposals/{proposal['id']}", headers=headers, json=proposal).status_code == 409
    duplicate = client.post("/groups/potential-proposals", headers=headers, json=proposal)
    assert duplicate.json()["id"] == proposal["id"]
    assert duplicate.json()["members"][0]["response"] == "reconfirm"
    assert len(client.get("/groups/potential-proposals", headers=headers).json()) == 1
    form = client.post("/groups/form", headers=headers, json={"name": "Not agreed", "student_ids": ids, "proposal_id": saved["id"], "proposal_version": saved["version"]})
    assert form.status_code == 409


def test_proposal_formation_is_single_use_and_requires_current_availability(client):
    headers, ids, proposal = setup_proposal(client)
    payload = {"name": "Agreed group", "student_ids": ids, "proposal_id": proposal["id"], "proposal_version": proposal["version"]}
    response = client.post("/groups/form", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    assert client.post("/groups/form", headers=headers, json={**payload, "name": "Duplicate"}).status_code == 409
    saved = client.get("/groups/potential-proposals", headers=headers).json()[0]
    assert saved["formed_group_id"] == response.json()["group"]["id"]
    assert client.put(f"/groups/potential-proposals/{proposal['id']}", headers=headers, json=proposal).status_code == 409


def test_changed_availability_blocks_formation(client):
    headers, ids, proposal = setup_proposal(client)
    response = client.put(f"/students/{ids[0]}/preferences", headers=headers, json={"preferred_location_id": None, "availability": [{"weekday": 1, "start_time": "18:00", "end_time": "20:00", "preference": "preferred"}]})
    assert response.status_code == 200
    formed = client.post("/groups/form", headers=headers, json={"name": "Outdated", "student_ids": ids, "proposal_id": proposal["id"], "proposal_version": proposal["version"]})
    assert formed.status_code == 409, formed.text


def test_schedule_start_date_and_conflicts(client):
    from datetime import date, timedelta, datetime
    # SQLite drops timezone offsets; use UTC for this shared SQLite/Postgres test.
    org = client.post("/organizations", json={"name": "Schedule", "slug": "future-schedule", "timezone": "UTC"}).json()
    headers = {"X-Organization-Id": org["id"]}
    location = client.post("/locations", headers=headers, json={"name": "Room"}).json()
    group = client.post("/groups/form", headers=headers, json={"name": "Future", "location_id": location["id"]}).json()["group"]
    starts = date.today() + timedelta(days=14)
    schedule = {"group_id": group["id"], "starts_on": starts.isoformat(), "slots": [{"weekday": starts.weekday(), "start_time": "17:00", "duration_minutes": 60}]}
    response = client.post("/group-schedules/batch", headers=headers, json=schedule)
    assert response.status_code == 201, response.text
    lessons = client.get("/lesson-sessions", headers=headers).json()
    assert lessons and all(datetime.fromisoformat(row["starts_at"]).date() >= starts for row in lessons)
    preview = client.post("/groups/potential-proposals/preview", headers=headers, json={"location_id": location["id"], "slots": [{"weekday": starts.weekday(), "start_time": "17:00", "end_time": "18:00"}]})
    assert preview.status_code == 200, preview.text
    assert preview.json() and "Future" in preview.json()[0]
    other = client.post("/groups/form", headers=headers, json={"name": "Other", "location_id": location["id"]}).json()["group"]
    conflict = client.post("/group-schedules/batch", headers=headers, json={**schedule, "group_id": other["id"]})
    assert conflict.status_code == 409, conflict.text
    assert client.get(f"/group-schedules?group_id={other['id']}", headers=headers).json() == []
