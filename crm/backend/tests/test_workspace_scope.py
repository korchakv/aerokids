from uuid import UUID

from app.db.session import SessionLocal
from app.models.core import StaffRole
from app.services import workspace_service


def test_workspace_service_teacher_scope_is_limited_to_assigned_groups(client):
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Teacher scope regression",
            "organization_slug": "teacher-scope-regression",
            "full_name": "Owner",
            "email": "owner-scope-regression@example.com",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    org_id = bootstrap.json()["organization_id"]
    owner_headers = {
        "Authorization": f"Bearer {bootstrap.json()['access_token']}",
        "X-Organization-Id": org_id,
    }

    group_a = client.post("/groups", headers=owner_headers, json={"name": "Assigned", "capacity": 8})
    group_b = client.post("/groups", headers=owner_headers, json={"name": "Foreign", "capacity": 8})
    assert group_a.status_code == 201, group_a.text
    assert group_b.status_code == 201, group_b.text

    invite = client.post(
        "/organization-invitations",
        headers=owner_headers,
        json={"email": "teacher-scope-regression@example.com", "role": "teacher"},
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
    teacher_user_id = accepted.json()["user"]["id"]

    staff_rows = client.get("/staff", headers=owner_headers)
    assert staff_rows.status_code == 200, staff_rows.text
    teacher = next(row for row in staff_rows.json() if row["email"] == "teacher-scope-regression@example.com")
    assigned = client.post(
        f"/staff/{teacher['id']}/groups",
        headers=owner_headers,
        json={"group_id": group_a.json()["id"], "is_primary": True},
    )
    assert assigned.status_code == 201, assigned.text

    with SessionLocal() as db:
        allowed = workspace_service.assigned_group_ids_for_user(
            db,
            UUID(org_id),
            UUID(teacher_user_id),
            StaffRole.TEACHER,
        )

    assert allowed == {UUID(group_a.json()["id"])}
    assert UUID(group_b.json()["id"]) not in allowed
