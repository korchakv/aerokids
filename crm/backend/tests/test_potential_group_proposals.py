def create_org(client, name, slug):
    response = client.post("/organizations", json={"name": name, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()


def make_waiting_student(client, headers, name, start="17:00"):
    student = client.post("/students", headers=headers, json={"first_name": name, "age_at_inquiry": 10}).json()
    ready = client.patch(f"/students/{student['id']}/lead-outcome", headers=headers, json={"crm_status": "waiting_for_group"})
    assert ready.status_code == 200, ready.text
    saved = client.put(f"/students/{student['id']}/preferences", headers=headers, json={
        "preferred_location_id": None,
        "availability": [{"weekday": 1, "start_time": start, "end_time": "19:00", "preference": "preferred"}],
    })
    assert saved.status_code == 200, saved.text
    return student["id"]


def test_proposal_is_saved_and_tenant_scoped(client):
    org = create_org(client, "School A", "potential-group-a")
    other_org = create_org(client, "School B", "potential-group-b")
    headers = {"X-Organization-Id": org["id"]}
    other_headers = {"X-Organization-Id": other_org["id"]}
    first = make_waiting_student(client, headers, "Anna")
    second = make_waiting_student(client, headers, "Bohdan", "17:30")
    other_student = make_waiting_student(client, other_headers, "Other")
    shift = client.put(f"/students/{first}/preferences", headers=headers, json={
        "preferred_location_id": None,
        "school_shift": "first",
        "availability": [{"weekday": 1, "start_time": "17:00", "end_time": "19:00", "preference": "preferred"}],
    })
    assert shift.status_code == 200, shift.text
    assert shift.json()["school_shift"] == "first"
    proposal = {
        "members": [
            {"student_id": first, "response": "not_contacted", "availability_snapshot": [{"weekday": 1, "start_time": "17:00", "end_time": "19:00", "preference": "preferred"}]},
            {"student_id": second, "response": "awaiting", "availability_snapshot": [{"weekday": 1, "start_time": "17:30", "end_time": "19:00", "preference": "preferred"}]},
        ],
        "slots": [{"weekday": 1, "start_time": "17:30", "end_time": "18:30", "exact_match": True}],
        "stale": False,
    }
    created = client.post("/groups/potential-proposals", headers=headers, json=proposal)
    assert created.status_code == 201, created.text
    proposal_id = created.json()["id"]
    assert created.json()["members"][1]["response"] == "awaiting"

    listed = client.get("/groups/potential-proposals", headers=headers)
    assert [item["id"] for item in listed.json()] == [proposal_id]
    assert client.get("/groups/potential-proposals", headers=other_headers).json() == []

    cross_tenant = {**proposal, "members": [proposal["members"][0], {**proposal["members"][1], "student_id": other_student}]}
    rejected = client.post("/groups/potential-proposals", headers=headers, json=cross_tenant)
    assert rejected.status_code == 422

    updated = {**proposal, "members": [{**proposal["members"][0], "response": "agreed"}, proposal["members"][1]]}
    saved = client.put(f"/groups/potential-proposals/{proposal_id}", headers=headers, json=updated)
    assert saved.status_code == 200, saved.text
    assert saved.json()["members"][0]["response"] == "agreed"
