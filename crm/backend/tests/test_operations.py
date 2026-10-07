from app.api import operations_router
from app.core.config import settings
from app.services import operations_auth


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
        "integrity": {
            "organizations": [],
            "summary": {
                "organization_count": 1,
                "critical_finding_types": 0,
                "warning_finding_types": 0,
                "ok": True,
            },
        },
    }


def test_daily_maintenance_requires_identity(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", None)
    response = client.post("/internal/operations/daily-maintenance")
    assert response.status_code == 401


def test_daily_maintenance_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "wrong"},
    )
    assert response.status_code == 401


def test_daily_maintenance_runs_with_valid_emergency_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    monkeypatch.setattr(operations_router, "run_daily_maintenance", _ok_result)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "m" * 40},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"


def test_daily_maintenance_runs_with_valid_github_oidc(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", None)
    monkeypatch.setattr(
        operations_router,
        "verify_github_actions_token",
        lambda token: {"repository": "korchakv/aerokids", "ref": "refs/heads/main"},
    )
    monkeypatch.setattr(operations_router, "run_daily_maintenance", _ok_result)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"Authorization": "Bearer test-oidc-token"},
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



def test_daily_maintenance_fails_scheduler_on_critical_integrity_finding(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    bad = _ok_result()
    bad["integrity"]["summary"]["critical_finding_types"] = 1
    bad["integrity"]["summary"]["ok"] = False
    monkeypatch.setattr(operations_router, "run_daily_maintenance", lambda: bad)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "m" * 40},
    )
    assert response.status_code == 500
    assert response.json()["detail"]["integrity"]["ok"] is False

def test_read_only_mode_blocks_daily_maintenance(client, monkeypatch):
    monkeypatch.setattr(settings, "maintenance_secret", "m" * 40)
    monkeypatch.setattr(settings, "read_only_mode", True)
    response = client.post(
        "/internal/operations/daily-maintenance",
        headers={"X-Maintenance-Secret": "m" * 40},
    )
    assert response.status_code == 503


def test_github_oidc_claims_are_strict(monkeypatch):
    class Key:
        key = "public-key"

    monkeypatch.setattr(operations_auth._jwks_client, "get_signing_key_from_jwt", lambda token: Key())
    monkeypatch.setattr(
        operations_auth.jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "repo:korchakv/aerokids:ref:refs/heads/main",
            "repository": "korchakv/aerokids",
            "ref": "refs/heads/main",
            "event_name": "schedule",
            "workflow_ref": "korchakv/aerokids/.github/workflows/crm-maintenance.yml@refs/heads/main",
        },
    )
    claims = operations_auth.verify_github_actions_token("test-token")
    assert claims["repository"] == "korchakv/aerokids"


def test_github_oidc_rejects_other_workflow(monkeypatch):
    class Key:
        key = "public-key"

    monkeypatch.setattr(operations_auth._jwks_client, "get_signing_key_from_jwt", lambda token: Key())
    monkeypatch.setattr(
        operations_auth.jwt,
        "decode",
        lambda *args, **kwargs: {
            "sub": "repo:korchakv/aerokids:ref:refs/heads/main",
            "repository": "korchakv/aerokids",
            "ref": "refs/heads/main",
            "event_name": "schedule",
            "workflow_ref": "korchakv/aerokids/.github/workflows/other.yml@refs/heads/main",
        },
    )
    try:
        operations_auth.verify_github_actions_token("test-token")
    except operations_auth.MaintenanceIdentityError:
        pass
    else:
        raise AssertionError("unexpected workflow must be rejected")
