# Stage 3 regression: group detail query count must stay bounded as membership grows.

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

from sqlalchemy import event

from app.db.session import engine


@contextmanager
def select_counter():
    statements: list[str] = []

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)


def _organization(client):
    response = client.post("/organizations", json={"name": "Batch Detail", "slug": "batch-detail"})
    assert response.status_code == 201, response.text
    return {"X-Organization-Id": response.json()["id"]}


def test_group_detail_query_count_does_not_scale_with_member_payments(client):
    headers = _organization(client)
    student_ids = []
    suffixes = ["А", "Б", "В", "Г", "Д", "Е", "Ж", "З", "И", "К", "Л", "М"]
    for suffix in suffixes:
        student = client.post(
            "/students",
            headers=headers,
            json={"first_name": f"Учень {suffix}", "age_at_inquiry": 10},
        )
        assert student.status_code == 201, student.text
        student_id = student.json()["id"]
        student_ids.append(student_id)
        status = client.patch(
            f"/students/{student_id}/crm-status",
            headers=headers,
            json={"crm_status": "waiting_for_group"},
        )
        assert status.status_code == 200, status.text

    first_contact = client.post(
        "/contacts",
        headers=headers,
        json={"full_name": "Перший контакт", "phone": "0671112233"},
    ).json()
    second_contact = client.post(
        "/contacts",
        headers=headers,
        json={"full_name": "Другий контакт", "phone": "0671112244"},
    ).json()
    for contact in (first_contact, second_contact):
        linked = client.post(
            f"/students/{student_ids[0]}/contacts",
            headers=headers,
            json={"contact_id": contact["id"], "relation": "parent", "is_primary": True},
        )
        assert linked.status_code == 201, linked.text

    formed = client.post(
        "/groups/form",
        headers=headers,
        json={"name": "Batch FPV", "capacity": 20, "student_ids": student_ids},
    )
    assert formed.status_code == 201, formed.text
    group_id = formed.json()["group"]["id"]

    plan = client.post(
        "/subscription-plans",
        headers=headers,
        json={"name": "Batch Plan", "price_minor": 200000, "period_days": 30, "lessons_included": 8},
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    for student_id in student_ids:
        charge = client.post(
            "/billing/charges",
            headers=headers,
            json={
                "student_id": student_id,
                "plan_id": plan_id,
                "group_id": group_id,
                "starts_on": date.today().isoformat(),
            },
        )
        assert charge.status_code == 201, charge.text

    with select_counter() as statements:
        detail = client.get(f"/groups/{group_id}/detail", headers=headers)

    assert detail.status_code == 200, detail.text
    assert len(detail.json()["members"]) == 12
    first_member = next(member for member in detail.json()["members"] if member["student_id"] == student_ids[0])
    assert first_member["contact_name"] == "Перший контакт"
    assert all(member["billing"]["plan_name"] == "Batch Plan" for member in detail.json()["members"])
    # The previous per-member/per-payment implementation grew linearly well
    # beyond this threshold. The batched projection stays bounded.
    assert len(statements) <= 15, "\n".join(statements)
