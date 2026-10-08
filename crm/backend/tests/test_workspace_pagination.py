from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.core import StaffRole, User
from app.services import workspace_service


def _bootstrap(client, slug: str = "stage3-pages"):
    response = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Stage 3 School",
            "organization_slug": slug,
            "full_name": "Owner",
            "email": f"owner-{slug}@example.com",
            "password": "very-secure-password",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return payload, {
        "Authorization": f"Bearer {payload['access_token']}",
        "X-Organization-Id": payload["organization_id"],
    }


def _create_student(client, headers, name: str, status: str = "active"):
    response = client.post("/students", headers=headers, json={"first_name": name, "age_at_inquiry": 10})
    assert response.status_code == 201, response.text
    student = response.json()
    lifecycle = client.patch(
        f"/students/{student['id']}/status",
        headers=headers,
        json={"student_status": status},
    )
    assert lifecycle.status_code == 200, lifecycle.text
    return student


def test_student_page_contract_filters_sorts_and_counts_in_database(client):
    _, headers = _bootstrap(client, "student-pages")
    for name in ("Anna", "Bohdan", "Daria", "Maksym", "Sofia"):
        _create_student(client, headers, name)
    _create_student(client, headers, "Paused", "paused")

    first = client.get("/workspace/students/page?limit=2&offset=0&sort=name", headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["total"] == 6
    assert first.json()["limit"] == 2
    assert first.json()["offset"] == 0
    assert [item["first_name"] for item in first.json()["items"]] == ["Anna", "Bohdan"]

    middle = client.get("/workspace/students/page?limit=2&offset=2&sort=name", headers=headers)
    assert middle.status_code == 200, middle.text
    assert [item["first_name"] for item in middle.json()["items"]] == ["Daria", "Maksym"]

    search = client.get("/workspace/students/page?q=Sof&limit=10", headers=headers)
    assert search.status_code == 200, search.text
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["first_name"] == "Sofia"

    paused = client.get("/workspace/students/page?status=paused&limit=10", headers=headers)
    assert paused.status_code == 200, paused.text
    assert paused.json()["total"] == 1
    assert paused.json()["items"][0]["first_name"] == "Paused"


def test_group_page_contract_searches_and_sorts_by_active_size(client):
    _, headers = _bootstrap(client, "group-pages")
    group_ids = {}
    for name in ("Alpha", "Beta", "Gamma"):
        response = client.post("/groups", headers=headers, json={"name": name, "capacity": 8})
        assert response.status_code == 201, response.text
        group_ids[name] = response.json()["id"]

    for student_name, group_name in zip(("Іван", "Олена", "Марко"), ("Beta", "Beta", "Gamma")):
        student = _create_student(client, headers, student_name)
        enrolled = client.post(
            "/enrollments",
            headers=headers,
            json={"student_id": student["id"], "group_id": group_ids[group_name]},
        )
        assert enrolled.status_code == 201, enrolled.text

    page = client.get("/workspace/groups/page?sort=size_desc&limit=2", headers=headers)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 3
    assert [(item["name"], item["enrolled_count"]) for item in page.json()["items"]] == [
        ("Beta", 2),
        ("Gamma", 1),
    ]

    search = client.get("/workspace/groups/page?q=Alpha&limit=10", headers=headers)
    assert search.status_code == 200, search.text
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["name"] == "Alpha"


def test_workspace_service_teacher_scope_returns_only_assigned_groups(client):
    bootstrap, headers = _bootstrap(client, "teacher-service-scope")
    group_a = client.post("/groups", headers=headers, json={"name": "Assigned", "capacity": 8}).json()
    group_b = client.post("/groups", headers=headers, json={"name": "Foreign", "capacity": 8}).json()

    invite = client.post(
        "/organization-invitations",
        headers=headers,
        json={"email": "stage3-teacher@example.com", "role": "teacher"},
    )
    assert invite.status_code == 201, invite.text
    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Викладач Тестовий",
            "password": "teacher-secure-password",
        },
    )
    assert accepted.status_code == 200, accepted.text

    staff = client.get("/staff", headers=headers)
    assert staff.status_code == 200, staff.text
    teacher = next(item for item in staff.json() if item["email"] == "stage3-teacher@example.com")
    assigned = client.post(
        f"/staff/{teacher['id']}/groups",
        headers=headers,
        json={"group_id": group_a["id"], "is_primary": True},
    )
    assert assigned.status_code == 201, assigned.text

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "stage3-teacher@example.com"))
        assert user is not None
        allowed = workspace_service.assigned_group_ids_for_user(
            db,
            UUID(bootstrap["organization_id"]),
            user.id,
            StaffRole.TEACHER,
        )

    assert allowed == {UUID(group_a["id"])}
    assert UUID(group_b["id"]) not in allowed
