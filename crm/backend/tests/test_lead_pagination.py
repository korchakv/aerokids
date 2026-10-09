from datetime import datetime, timedelta, timezone


def _bootstrap(client):
    response = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "Lead Page School",
            "organization_slug": "lead-pages",
            "full_name": "Owner",
            "email": "lead-pages-owner@example.com",
            "password": "very-secure-password",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    return {
        "Authorization": f"Bearer {payload['access_token']}",
        "X-Organization-Id": payload["organization_id"],
    }


def _lead(client, headers, name: str):
    response = client.post("/students", headers=headers, json={"first_name": name, "age_at_inquiry": 10})
    assert response.status_code == 201, response.text
    return response.json()


def _status(client, headers, student_id: str, status: str):
    response = client.patch(
        f"/students/{student_id}/crm-status",
        headers=headers,
        json={"crm_status": status},
    )
    assert response.status_code == 200, response.text


def test_lead_page_filters_columns_searches_and_counts(client):
    headers = _bootstrap(client)
    new_lead = _lead(client, headers, "Новий")
    waiting = _lead(client, headers, "Очікує")
    _status(client, headers, waiting["id"], "waiting_for_group")

    closed = _lead(client, headers, "Закритий")
    outcome = client.patch(
        f"/students/{closed['id']}/lead-outcome",
        headers=headers,
        json={"crm_status": "declined", "close_reason": "not_interested"},
    )
    assert outcome.status_code == 200, outcome.text

    deferred = _lead(client, headers, "Відкладений")
    deferred_response = client.patch(
        f"/students/{deferred['id']}/defer",
        headers=headers,
        json={
            "deferred_until": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
            "reason": "later",
            "note": "Повернутися пізніше",
        },
    )
    assert deferred_response.status_code == 200, deferred_response.text

    contacted = _lead(client, headers, "Пропустив")
    _status(client, headers, contacted["id"], "contacted")
    trial = client.post(
        "/trial-lessons",
        headers=headers,
        json={
            "student_id": contacted["id"],
            "starts_at": (datetime.now(timezone.utc) + timedelta(days=1)).replace(minute=0, second=0, microsecond=0).isoformat(),
        },
    )
    assert trial.status_code == 201, trial.text
    no_show = client.patch(
        f"/trial-lessons/{trial.json()['id']}/complete",
        headers=headers,
        json={"status": "no_show"},
    )
    assert no_show.status_code == 200, no_show.text

    page = client.get("/workspace/leads/page?limit=2&sort=newest", headers=headers)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 5
    assert len(page.json()["items"]) == 2

    waiting_page = client.get("/workspace/leads/page?column=waiting&limit=10", headers=headers)
    assert waiting_page.status_code == 200, waiting_page.text
    assert waiting_page.json()["total"] == 1
    assert waiting_page.json()["items"][0]["student_id"] == waiting["id"]

    deferred_page = client.get("/workspace/leads/page?column=deferred&limit=10", headers=headers)
    assert deferred_page.status_code == 200, deferred_page.text
    assert deferred_page.json()["total"] == 1
    assert deferred_page.json()["items"][0]["student_id"] == deferred["id"]

    no_show_page = client.get("/workspace/leads/page?column=no_show&limit=10", headers=headers)
    assert no_show_page.status_code == 200, no_show_page.text
    assert no_show_page.json()["total"] == 1
    assert no_show_page.json()["items"][0]["student_id"] == contacted["id"]

    search = client.get("/workspace/leads/page?q=%D0%9E%D1%87%D1%96%D0%BA&limit=10", headers=headers)
    assert search.status_code == 200, search.text
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["student_id"] == waiting["id"]

    counts = client.get("/workspace/leads/counts", headers=headers)
    assert counts.status_code == 200, counts.text
    payload = counts.json()
    assert payload["new"] == 1
    assert payload["waiting"] == 1
    assert payload["deferred"] == 1
    assert payload["closed"] == 1
    assert payload["no_show"] == 1
    assert sum(payload.values()) == 5


def test_lead_page_is_tenant_scoped(client):
    first = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "First",
            "organization_slug": "lead-page-first",
            "full_name": "Owner First",
            "email": "lead-first@example.com",
            "password": "very-secure-password",
        },
    )
    assert first.status_code == 201, first.text
    first_headers = {
        "Authorization": f"Bearer {first.json()['access_token']}",
        "X-Organization-Id": first.json()["organization_id"],
    }
    _lead(client, first_headers, "Перший")

    second = client.post(
        "/organizations",
        headers=first_headers,
        json={"name": "Second", "slug": "lead-page-second"},
    )
    assert second.status_code == 201, second.text
    # Test mode allows an unauthenticated owner scope; do not reuse the first
    # tenant's bearer token for the second tenant.
    second_headers = {"X-Organization-Id": second.json()["id"]}
    _lead(client, second_headers, "Другий")

    first_page = client.get("/workspace/leads/page?limit=10", headers=first_headers)
    second_page = client.get("/workspace/leads/page?limit=10", headers=second_headers)
    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    assert [item["first_name"] for item in first_page.json()["items"]] == ["Перший"]
    assert [item["first_name"] for item in second_page.json()["items"]] == ["Другий"]
