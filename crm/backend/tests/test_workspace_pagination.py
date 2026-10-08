def _bootstrap(client, slug: str):
    result = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Pagination School",
            "organization_slug": slug,
            "full_name": "Owner",
            "email": f"owner-{slug}@example.com",
            "password": "very-secure-password",
        },
    )
    assert result.status_code == 201, result.text
    return {
        "Authorization": f"Bearer {result.json()['access_token']}",
        "X-Organization-Id": result.json()["organization_id"],
    }


def test_workspace_leads_and_groups_have_stable_server_pages(client):
    headers = _bootstrap(client, "pagination-pages")

    for index in range(5):
        created = client.post(
            "/students",
            headers=headers,
            json={"first_name": f"Lead {index}", "age_at_inquiry": 10 + index},
        )
        assert created.status_code == 201, created.text

    first_page = client.get("/workspace/leads-page?limit=2&offset=0", headers=headers)
    assert first_page.status_code == 200, first_page.text
    payload = first_page.json()
    assert payload["total"] == 5
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert payload["has_more"] is True
    assert len(payload["items"]) == 2

    last_page = client.get("/workspace/leads-page?limit=2&offset=4", headers=headers)
    assert last_page.status_code == 200, last_page.text
    assert last_page.json()["total"] == 5
    assert len(last_page.json()["items"]) == 1
    assert last_page.json()["has_more"] is False

    filtered = client.get("/workspace/leads-page?q=Lead%204", headers=headers)
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["first_name"] == "Lead 4"

    for name in ("Gamma", "Alpha", "Beta"):
        created = client.post("/groups", headers=headers, json={"name": name, "capacity": 8})
        assert created.status_code == 201, created.text

    groups = client.get("/workspace/groups-page?limit=2&sort=name&order=asc", headers=headers)
    assert groups.status_code == 200, groups.text
    assert groups.json()["total"] == 3
    assert [item["name"] for item in groups.json()["items"]] == ["Alpha", "Beta"]
    assert groups.json()["has_more"] is True


def test_workspace_group_page_preserves_assigned_teacher_scope(client):
    headers = _bootstrap(client, "pagination-teacher-scope")
    assigned_group = client.post("/groups", headers=headers, json={"name": "Assigned", "capacity": 8})
    foreign_group = client.post("/groups", headers=headers, json={"name": "Foreign", "capacity": 8})
    assert assigned_group.status_code == 201, assigned_group.text
    assert foreign_group.status_code == 201, foreign_group.text

    invite = client.post(
        "/organization-invitations",
        headers=headers,
        json={"email": "pagination-teacher@example.com", "role": "teacher"},
    )
    assert invite.status_code == 201, invite.text
    accepted = client.post(
        "/auth/accept-invite",
        json={
            "invite_token": invite.json()["invite_token"],
            "full_name": "Pagination Teacher",
            "password": "teacher-secure-password",
        },
    )
    assert accepted.status_code == 200, accepted.text

    staff = client.get("/staff", headers=headers)
    assert staff.status_code == 200, staff.text
    teacher = next(item for item in staff.json() if item["email"] == "pagination-teacher@example.com")
    assignment = client.post(
        f"/staff/{teacher['id']}/groups",
        headers=headers,
        json={"group_id": assigned_group.json()["id"], "is_primary": True},
    )
    assert assignment.status_code == 201, assignment.text

    teacher_headers = {
        "Authorization": f"Bearer {accepted.json()['access_token']}",
        "X-Organization-Id": headers["X-Organization-Id"],
    }
    page = client.get("/workspace/groups-page", headers=teacher_headers)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert [item["name"] for item in page.json()["items"]] == ["Assigned"]
