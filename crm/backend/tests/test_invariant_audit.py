from datetime import datetime
from uuid import UUID

from app.db.session import SessionLocal
from app.jobs.audit_invariants import audit_organization
from app.models.core import Organization, TrialLesson, TrialStatus


def test_invariant_auditor_reports_legacy_trial_overlap(client):
    org_response = client.post("/organizations", json={"name": "Audit School", "slug": "audit-schedule-conflict"})
    assert org_response.status_code == 201, org_response.text
    org_id = org_response.json()["id"]
    headers = {"X-Organization-Id": org_id}

    location = client.post("/locations", headers=headers, json={"name": "Main"}).json()
    first = client.post("/students", headers=headers, json={"first_name": "First", "age_at_inquiry": 10}).json()
    second = client.post("/students", headers=headers, json={"first_name": "Second", "age_at_inquiry": 11}).json()

    with SessionLocal() as db:
        start = datetime.fromisoformat("2026-10-10T10:00:00+03:00")
        db.add_all([
            TrialLesson(
                organization_id=UUID(org_id),
                location_id=UUID(location["id"]),
                student_id=UUID(first["id"]),
                starts_at=start,
                status=TrialStatus.SCHEDULED,
            ),
            TrialLesson(
                organization_id=UUID(org_id),
                location_id=UUID(location["id"]),
                student_id=UUID(second["id"]),
                starts_at=start,
                status=TrialStatus.SCHEDULED,
            ),
        ])
        db.commit()

        organization = db.get(Organization, UUID(org_id))
        findings = audit_organization(db, organization)

    conflict = next(item for item in findings if item.code == "scheduled_resource_conflicts")
    assert conflict.severity == "warning"
    assert conflict.count == 1
