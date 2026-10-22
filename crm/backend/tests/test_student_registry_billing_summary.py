from datetime import date


def test_student_registry_includes_paid_lesson_and_next_payment_summary(client):
    organization = client.post("/organizations", json={
        "name": "Student Billing School",
        "slug": "student-billing-school",
    })
    assert organization.status_code == 201, organization.text
    headers = {"X-Organization-Id": organization.json()["id"]}

    student = client.post("/students", headers=headers, json={
        "first_name": "Олена",
        "age_at_inquiry": 10,
    })
    assert student.status_code == 201, student.text
    student_id = student.json()["id"]
    active = client.patch(f"/students/{student_id}/status", headers=headers, json={"student_status": "active"})
    assert active.status_code == 200, active.text

    plan = client.post("/subscription-plans", headers=headers, json={
        "name": "8 занять",
        "price_minor": 200000,
        "period_days": 30,
        "lessons_included": 8,
    })
    assert plan.status_code == 201, plan.text

    due_date = "2099-10-15"
    charge = client.post("/billing/charges", headers=headers, json={
        "student_id": student_id,
        "plan_id": plan.json()["id"],
        "starts_on": date.today().isoformat(),
        "due_date": due_date,
    })
    assert charge.status_code == 201, charge.text

    page = client.get("/workspace/students/page", headers=headers)
    assert page.status_code == 200, page.text
    row = next(item for item in page.json()["items"] if item["student_id"] == student_id)
    assert row["billing"] == {
        "paid_lessons": 0,
        "lessons_used": 0,
        "lessons_included": 8,
        "next_due_date": due_date,
    }

    paid = client.patch(f"/payments/{charge.json()['payment']['id']}/paid", headers=headers, json={"method": "cash"})
    assert paid.status_code == 200, paid.text
    page_after_payment = client.get("/workspace/students/page", headers=headers)
    row_after_payment = next(item for item in page_after_payment.json()["items"] if item["student_id"] == student_id)
    assert row_after_payment["billing"]["paid_lessons"] == 8
    assert row_after_payment["billing"]["next_due_date"] is None
