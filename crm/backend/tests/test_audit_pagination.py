from __future__ import annotations


def _org(client, slug: str):
    response = client.post("/organizations", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    org_id = response.json()["id"]
    return org_id, {"X-Organization-Id": org_id}


def test_audit_page_is_paginated_filterable_and_tenant_scoped(client):
    org_id, headers = _org(client, "audit-page-primary")
    _, foreign_headers = _org(client, "audit-page-foreign")

    for name in ("Audit One", "Audit Two", "Audit Three"):
        response = client.patch("/organization", headers=headers, json={"name": name})
        assert response.status_code == 200, response.text

    foreign = client.patch("/organization", headers=foreign_headers, json={"name": "Foreign Audit"})
    assert foreign.status_code == 200, foreign.text

    page = client.get("/audit-events/page?limit=2&offset=0", headers=headers)
    assert page.status_code == 200, page.text
    payload = page.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert len(payload["items"]) == 2
    assert {item["organization_id"] for item in payload["items"]} == {org_id}

    next_page = client.get("/audit-events/page?limit=2&offset=2", headers=headers)
    assert next_page.status_code == 200, next_page.text
    assert next_page.json()["total"] == 3
    assert len(next_page.json()["items"]) == 1

    filtered = client.get(
        "/audit-events/page?entity_type=organization&event_type=organization.settings_updated&q=settings&limit=10",
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert filtered.json()["total"] == 3
    assert all(item["entity_type"] == "organization" for item in filtered.json()["items"])
    assert all(item["event_type"] == "organization.settings_updated" for item in filtered.json()["items"])

    oldest = client.get("/audit-events/page?sort=oldest&limit=10", headers=headers)
    assert oldest.status_code == 200, oldest.text
    names = [item["payload"]["name"] for item in oldest.json()["items"]]
    assert names == ["Audit One", "Audit Two", "Audit Three"]


def test_legacy_entity_audit_endpoint_remains_bounded(client):
    org_id, headers = _org(client, "audit-page-legacy")
    for index in range(3):
        response = client.patch("/organization", headers=headers, json={"name": f"Legacy Audit {index}"})
        assert response.status_code == 200, response.text

    response = client.get(
        f"/audit-events?entity_type=organization&entity_id={org_id}&limit=2",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 2
