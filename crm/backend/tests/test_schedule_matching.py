from datetime import time
from uuid import UUID

import pytest

from app.models.core import AvailabilityPreference, AuditEvent, Enrollment
from app.db.session import SessionLocal
from app.services.schedule_matching import evaluate_schedule_match


def slot(day=0, start="17:00", duration=60):
    return {"weekday": day, "start_time": start, "duration_minutes": duration}


def window(day=0, start="16:30", end="19:00", preference="preferred"):
    return {"weekday": day, "start_time": time.fromisoformat(start), "end_time": time.fromisoformat(end), "preference": preference}


@pytest.mark.parametrize(("windows", "expected"), [
    ([window()], "match"),
    ([window(start="17:30", end="19:00")], "partial"),
    ([window(start="18:30", end="20:00")], "partial"),
    ([window(day=1)], "conflict"),
    ([window(preference="avoid")], "conflict"),
    ([], "unknown"),
])
def test_schedule_match_statuses(windows, expected):
    assert evaluate_schedule_match([slot()], windows).status == expected


def test_multiple_slots_and_location_mismatch_are_partial():
    result = evaluate_schedule_match(
        [slot(), slot(day=2)], [window(), window(day=2)],
        group_location_id="group", preferred_location_id="preferred",
    )
    assert result.status == "partial"
    assert len(result.matching_slots) == 2


def create_org(client, name, slug):
    response = client.post("/organizations", json={"name": name, "slug": slug})
    assert response.status_code == 201
    return response.json()


def waiting_student(client, headers, name):
    student = client.post("/students", headers=headers, json={"first_name": name, "age_at_inquiry": 10}).json()
    client.patch(f"/students/{student['id']}/crm-status", headers=headers, json={"crm_status": "waiting_for_group"})
    return student


def test_preference_defaults_validation_and_preview_tenant_scope(client):
    org_a = create_org(client, "Schedule A", "schedule-a")
    org_b = create_org(client, "Schedule B", "schedule-b")
    a = {"X-Organization-Id": org_a["id"]}
    b = {"X-Organization-Id": org_b["id"]}
    student = waiting_student(client, a, "Марко")
    foreign = waiting_student(client, b, "Інший")

    saved = client.put(f"/students/{student['id']}/preferences", headers=a, json={
        "availability": [{"weekday": 0, "start_time": "16:30", "end_time": "19:00"}],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["availability"][0]["preference"] == "preferred"

    invalid_range = client.put(f"/students/{student['id']}/preferences", headers=a, json={
        "availability": [{"weekday": 0, "start_time": "17:00", "end_time": "17:00"}],
    })
    assert invalid_range.status_code == 422
    invalid_boundary = client.post("/groups/form", headers=a, json={
        "name": "Invalid", "student_ids": [student["id"]],
        "schedule_slots": [{"weekday": 0, "start_time": "17:10", "duration_minutes": 60}],
    })
    assert invalid_boundary.status_code == 422

    preview = client.post("/groups/match-preview", headers=a, json={
        "schedule_slots": [slot()], "student_ids": [student["id"]],
    })
    assert preview.status_code == 200, preview.text
    assert preview.json()["students"][0]["status"] == "match"
    leaked = client.post("/groups/match-preview", headers=a, json={
        "schedule_slots": [slot()], "student_ids": [foreign["id"]],
    })
    assert leaked.status_code == 404


def test_group_formation_persists_advisory_match_and_audit(client):
    org = create_org(client, "Formation", "formation-match")
    headers = {"X-Organization-Id": org["id"]}
    student = waiting_student(client, headers, "Софія")
    client.put(f"/students/{student['id']}/preferences", headers=headers, json={
        "availability": [{"weekday": 1, "start_time": "18:00", "end_time": "20:00", "preference": "preferred"}],
    })
    formed = client.post("/groups/form", headers=headers, json={
        "name": "Monday Group", "capacity": 8, "student_ids": [student["id"]],
        "schedule_slots": [slot()],
    })
    assert formed.status_code == 201, formed.text

    with SessionLocal() as db:
        enrollment = db.query(Enrollment).filter(Enrollment.student_id == UUID(student["id"])).one()
        assert enrollment.schedule_match == "conflict"
        assert "Потрібно підтвердити" in enrollment.schedule_note
        event = db.query(AuditEvent).filter(AuditEvent.event_type == "student.enrolled").one()
        assert event.payload["schedule_match"] == "conflict"
        assert event.payload["schedule_note"] == enrollment.schedule_note


def test_duplicate_group_slots_rejected(client):
    org = create_org(client, "Duplicates", "duplicate-slots")
    headers = {"X-Organization-Id": org["id"]}
    student = waiting_student(client, headers, "Олег")
    response = client.post("/groups/form", headers=headers, json={
        "name": "Duplicate", "student_ids": [student["id"]],
        "schedule_slots": [slot(), slot()],
    })
    assert response.status_code == 422
