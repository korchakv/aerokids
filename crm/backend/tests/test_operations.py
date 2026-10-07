from app.api import operations_router
from app.core.config import settings


def _ok_result():
    return {
        "organizations": [{
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "organization_name": "Test",
            "reconciled_groups": 0,
            "created_lesson_sessions": 0,
            "billing": {"created_subscriptions": 0},
            "rule_snapshots_created": 0,
            "errors": [],
        }],
        "throttle_cleanup": {"auth_login": 0, "public_intake": 0},
        "transactional_email": {"enabled": False, "sent": 0, "failed": 0, "pending": 0},
    }


def test_daily_maintenance_is_closed_when_not_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", None)
    response = client.post("/internal/operations/daily-maintenance")
    assert response.status_code == 503


def test_daily_maintenance_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_daily_maintenance_runs_with_valid_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    monkeypatch.setattr(operations_router, "run_daily_maintenance", _ok_result)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "m" * 40},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_daily_maintenance_fails_scheduler_on_partial_error(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    bad = _ok_result()
    bad["organizations"][0]["errors"] = [{"billing": "boom"}]
    monkeypatch.setattr(operations_router, "run_daily_maintenance", lambda: bad)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "m" * 40},
    )
    assert response.status_code == 500
    assert response.json()["detail"]["status"] == "degraded"


def test_read_only_mode_blocks_daily_maintenance(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    monkeypatch.setattr(settings, "read_only_mode", True)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "m" * 40},
    )
    assert response.status_code == 503
