#!/usr/bin/env python3
import json
import sys
import time
import urllib.error
import urllib.request


API = "http://localhost:8000"
WEB = "http://localhost:8080"


def request(path, method="GET", body=None, headers=None, base=API):
    data = None if body is None else json.dumps(body).encode("utf-8")
    merged = {"Content-Type": "application/json"}
    if headers:
        merged.update(headers)
    req = urllib.request.Request(base + path, data=data, method=method, headers=merged)
    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read()
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.status, json.loads(raw.decode("utf-8"))
        return response.status, raw.decode("utf-8")


def wait_for(path, base=API, attempts=60):
    last_error = None
    for _ in range(attempts):
        try:
            status, payload = request(path, base=base)
            if 200 <= status < 500:
                return status, payload
        except Exception as exc:
            last_error = exc
        time.sleep(2)
    raise RuntimeError(f"Service did not become ready: {base}{path}: {last_error}")


def main():
    status, health = wait_for("/health")
    assert status == 200 and health["status"] == "ok", health

    status, html = wait_for("/", base=WEB)
    assert status == 200 and ("AeroKids" in html or "AeroKiDS" in html or 'id="root"' in html), "Frontend did not serve the CRM shell"

    status, bootstrap = request("/auth/bootstrap", "POST", {
        "organization_name": "Smoke School",
        "organization_slug": "smoke-school",
        "full_name": "Smoke Owner",
        "email": "owner@smoke.test",
        "password": "smoke-test-password-123",
    }, headers={"X-Bootstrap-Secret": "local-bootstrap-secret-change-before-public-deploy"})
    assert status == 201, bootstrap
    token = bootstrap["access_token"]
    organization_id = bootstrap["organization_id"]
    auth = {
        "Authorization": f"Bearer {token}",
        "X-Organization-Id": organization_id,
    }

    status, me = request("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert status == 200 and me["memberships"][0]["organization_id"] == organization_id, me

    status, location = request("/locations", "POST", {
        "name": "Smoke Location",
        "address": "Integration test",
    }, auth)
    assert status == 201, location

    status, intake = request("/intake", "POST", {
        "child_first_name": "Test Child",
        "child_age": 10,
        "contact_name": "Test Parent",
        "phone": "+380671234567",
        "source": "smoke",
        "comment": "Full-stack smoke test",
    }, auth)
    assert status == 201, intake

    student_id = intake["student_id"]
    status, trial = request("/trial-lessons", "POST", {
        "student_id": student_id,
        "location_id": location["id"],
        "starts_at": "2026-10-15T17:00:00+03:00",
    }, auth)
    assert status == 201, trial

    status, leads = request("/workspace/leads", headers=auth)
    assert status == 200 and any(item["student_id"] == student_id for item in leads), leads

    print("Full-stack smoke test passed: web + API + PostgreSQL + auth + CRM workflow")


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, urllib.error.HTTPError, urllib.error.URLError, RuntimeError) as exc:
        print(f"Smoke test failed: {exc}", file=sys.stderr)
        sys.exit(1)
