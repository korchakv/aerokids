def create_org(client, name, slug):
    response = client.post("/organizations", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_public_intake_creates_student_and_contact(client):
    org = create_org(client, "AeroKiDS", "aerokids")
    response = client.post("/public/intake/aerokids", json={
        "child_first_name": "Максим",
        "child_age": 9,
        "contact_name": "Оксана",
        "phone": "0671234567",
        "comment": "Цікавиться FPV",
    })
    assert response.status_code == 201, response.text
    assert response.json()["crm_status"] == "new"
    headers = {"X-Organization-Id": org["id"]}
    students = client.get("/students", headers=headers)
    contacts = client.get("/contacts", headers=headers)
    assert len(students.json()) == 1
    assert contacts.json()[0]["phone"] == "+380671234567"


def test_tenant_isolation_on_students(client):
    org_a = create_org(client, "School A", "school-a")
    org_b = create_org(client, "School B", "school-b")
    client.post("/students", headers={"X-Organization-Id": org_a["id"]}, json={"first_name": "Anna", "age_at_inquiry": 10})
    client.post("/students", headers={"X-Organization-Id": org_b["id"]}, json={"first_name": "Bohdan", "age_at_inquiry": 11})
    a_students = client.get("/students", headers={"X-Organization-Id": org_a["id"]}).json()
    b_students = client.get("/students", headers={"X-Organization-Id": org_b["id"]}).json()
    assert [s["first_name"] for s in a_students] == ["Anna"]
    assert [s["first_name"] for s in b_students] == ["Bohdan"]


def test_cross_tenant_contact_link_is_blocked(client):
    org_a = create_org(client, "School A", "school-a")
    org_b = create_org(client, "School B", "school-b")
    student = client.post("/students", headers={"X-Organization-Id": org_a["id"]}, json={"first_name": "Anna"}).json()
    contact = client.post("/contacts", headers={"X-Organization-Id": org_b["id"]}, json={"full_name": "Other Parent", "phone": "0501234567"}).json()
    response = client.post(f"/students/{student['id']}/contacts", headers={"X-Organization-Id": org_a["id"]}, json={"contact_id": contact["id"], "relation": "parent", "is_primary": True})
    assert response.status_code == 404
