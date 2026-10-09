# Rebased regression: payment pagination must pass with Stage 3 performance guards.
# Stage 3 regression: payment pages must stay tenant-scoped and ledger-aggregated in SQL.
def _org(client, slug: str):
    response = client.post("/organizations", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return {"X-Organization-Id": response.json()["id"]}


def test_payment_page_aggregates_ledger_and_filters_overdue(client):
    headers = _org(client, "payment-pages")
    student = client.post("/students", headers=headers, json={"first_name": "Марко"}).json()
    contact = client.post(
        "/contacts",
        headers=headers,
        json={"full_name": "Олена Платник", "phone": "0671112233"},
    ).json()
    linked = client.post(
        f"/students/{student['id']}/contacts",
        headers=headers,
        json={"contact_id": contact["id"], "relation": "parent", "is_primary": True},
    )
    assert linked.status_code == 201, linked.text

    overdue = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 100000, "due_date": "2000-01-01", "note": "Жовтень"},
    ).json()
    receipt = client.post(
        f"/payments/{overdue['id']}/receipts",
        headers=headers,
        json={"amount_minor": 30000, "method": "cash"},
    )
    assert receipt.status_code == 201, receipt.text
    adjusted = client.post(
        f"/payments/{overdue['id']}/adjustments",
        headers=headers,
        json={"direction": "decrease", "amount_minor": 10000, "reason": "Знижка"},
    )
    assert adjusted.status_code == 201, adjusted.text

    paid = client.post(
        "/payments",
        headers=headers,
        json={"student_id": student["id"], "amount_minor": 50000, "due_date": "2099-01-01"},
    ).json()
    settled = client.patch(f"/payments/{paid['id']}/paid", headers=headers, json={"method": "card"})
    assert settled.status_code == 200, settled.text

    page = client.get("/payments/page?limit=10&sort=due", headers=headers)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 2
    first = page.json()["items"][0]
    assert first["id"] == overdue["id"]
    assert first["student_name"] == "Марко"
    assert first["contact_name"] == "Олена Платник"
    assert first["adjusted_amount_minor"] == 90000
    assert first["paid_minor"] == 30000
    assert first["refunded_minor"] == 0
    assert first["balance_minor"] == 60000

    overdue_page = client.get("/payments/page?overdue=true&limit=10", headers=headers)
    assert overdue_page.status_code == 200, overdue_page.text
    assert overdue_page.json()["total"] == 1
    assert overdue_page.json()["items"][0]["id"] == overdue["id"]

    paid_page = client.get("/payments/page?status=paid&limit=10", headers=headers)
    assert paid_page.status_code == 200, paid_page.text
    assert paid_page.json()["total"] == 1
    assert paid_page.json()["items"][0]["id"] == paid["id"]
    assert paid_page.json()["items"][0]["balance_minor"] == 0

    search = client.get("/payments/page?q=%D0%9F%D0%BB%D0%B0%D1%82%D0%BD%D0%B8%D0%BA&limit=10", headers=headers)
    assert search.status_code == 200, search.text
    assert search.json()["total"] == 2


def test_payment_page_is_paginated_and_tenant_scoped(client):
    first = _org(client, "payment-pages-first")
    second = _org(client, "payment-pages-second")
    first_student = client.post("/students", headers=first, json={"first_name": "Перший"}).json()
    second_student = client.post("/students", headers=second, json={"first_name": "Другий"}).json()

    for amount in (10000, 20000, 30000):
        response = client.post("/payments", headers=first, json={"student_id": first_student["id"], "amount_minor": amount})
        assert response.status_code == 201, response.text
    foreign = client.post("/payments", headers=second, json={"student_id": second_student["id"], "amount_minor": 99000})
    assert foreign.status_code == 201, foreign.text

    page = client.get("/payments/page?limit=2&offset=0", headers=first)
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 3
    assert len(page.json()["items"]) == 2
    assert {item["student_id"] for item in page.json()["items"]} == {first_student["id"]}

    next_page = client.get("/payments/page?limit=2&offset=2", headers=first)
    assert next_page.status_code == 200, next_page.text
    assert len(next_page.json()["items"]) == 1
    assert next_page.json()["items"][0]["student_id"] == first_student["id"]
