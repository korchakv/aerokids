from datetime import datetime, timedelta, timezone
from threading import Event, Thread
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.models.core import Organization
from app.models.hardening_extensions import NotificationOutbox
from app.services import notifications


@pytest.fixture(autouse=True)
def release_worker_connections(clean_db):
    yield
    # These tests use independent worker sessions as well as HTTP sessions.
    # Release their pool before another test rebuilds the SQLite schema.
    engine.dispose()


@pytest.fixture
def smtp(monkeypatch):
    sent = []

    class SMTP:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def starttls(self):
            pass

        def login(self, *args):
            pass

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(settings, "transactional_email_enabled", True)
    monkeypatch.setattr(settings, "smtp_from_email", "sender@example.com")
    monkeypatch.setattr(notifications.smtplib, "SMTP", SMTP)
    return sent, SMTP


def queued(expiry=None):
    with SessionLocal() as db:
        org = Organization(name="Email test", slug=str(uuid4()))
        db.add(org)
        db.flush()
        row = notifications.enqueue_password_reset(db, org.id, "owner@example.com", "test-reset-token", org.name,
                                                   expires_at=expiry or datetime.now(timezone.utc) + timedelta(hours=1))
        db.commit()
        return org.id, row.id


def test_delivery_removes_credentials_and_is_not_sent_again(smtp):
    org_id, row_id = queued()
    notifications.deliver_one(org_id, row_id)
    notifications.deliver_one(org_id, row_id)
    assert len(smtp[0]) == 1
    assert "test-reset-token" in smtp[0][0].get_content()
    with SessionLocal() as db:
        row = db.get(NotificationOutbox, row_id)
        assert row.status == "sent" and row.attempts == 1
        assert "test-reset-token" not in str(row.payload)


def test_delivery_is_tenant_scoped(smtp):
    _, row_id = queued()
    notifications.deliver_one(uuid4(), row_id)
    assert smtp[0] == []


def test_expired_reset_is_not_sent_and_token_is_removed(smtp):
    org_id, row_id = queued(datetime.now(timezone.utc) - timedelta(seconds=1))
    notifications.deliver_one(org_id, row_id)
    assert smtp[0] == []
    with SessionLocal() as db:
        row = db.get(NotificationOutbox, row_id)
        assert row.status == "expired" and row.attempts == 0
        assert "test-reset-token" not in str(row.payload)


def test_failed_delivery_can_retry_and_does_not_store_provider_secrets(smtp, monkeypatch):
    org_id, row_id = queued()
    original = smtp[1].send_message

    def fail(self, message):
        raise RuntimeError("private-provider-data test-reset-token")

    monkeypatch.setattr(smtp[1], "send_message", fail)
    notifications.deliver_one(org_id, row_id)
    with SessionLocal() as db:
        row = db.get(NotificationOutbox, row_id)
        assert row.status == "failed" and row.attempts == 1
        assert row.last_error == "RuntimeError"
        assert "link" in row.payload
    monkeypatch.setattr(smtp[1], "send_message", original)
    notifications.deliver_one(org_id, row_id)
    assert len(smtp[0]) == 1
    with SessionLocal() as db:
        assert db.get(NotificationOutbox, row_id).attempts == 2


def test_retry_limit_stops_delivery(smtp):
    org_id, row_id = queued()
    with SessionLocal() as db:
        row = db.get(NotificationOutbox, row_id)
        row.status = "failed"
        row.attempts = 5
        db.commit()
    notifications.deliver_one(org_id, row_id)
    assert smtp[0] == []


def test_expired_exhausted_message_also_cleans_credential(smtp):
    org_id, row_id = queued(datetime.now(timezone.utc) - timedelta(seconds=1))
    with SessionLocal() as db:
        row = db.get(NotificationOutbox, row_id)
        row.status = "failed"
        row.attempts = 5
        db.commit()
    notifications.deliver_one(org_id, row_id)
    assert smtp[0] == []
    with SessionLocal() as db:
        row = db.get(NotificationOutbox, row_id)
        assert row.status == "expired" and "link" not in row.payload


def test_maintenance_scrubs_expiry_when_email_is_disabled(smtp, monkeypatch):
    _, expired_id = queued(datetime.now(timezone.utc) - timedelta(seconds=1))
    _, valid_id = queued()
    monkeypatch.setattr(settings, "transactional_email_enabled", False)
    with SessionLocal() as db:
        result = notifications.deliver_pending(db)
        assert result["enabled"] is False and result["expired"] == 1 and result["pending"] == 1
        assert db.get(NotificationOutbox, expired_id).status == "expired"
        assert db.get(NotificationOutbox, valid_id).status == "pending"
    assert smtp[0] == []


@pytest.mark.parametrize("flag", ["read_only_mode", "transactional_email_enabled"])
def test_delivery_respects_disabled_or_read_only_mode(smtp, monkeypatch, flag):
    org_id, row_id = queued()
    monkeypatch.setattr(settings, flag, flag == "read_only_mode")
    notifications.deliver_one(org_id, row_id)
    assert smtp[0] == []
    with SessionLocal() as db:
        assert db.get(NotificationOutbox, row_id).attempts == 0


@pytest.mark.parametrize("route,data", [
    ("/password-reset-links", {"email": "owner-email@example.com"}),
    ("/organization-invitations", {"email": "teacher-email@example.com", "role": "teacher", "can_teach": True}),
])
def test_auth_routes_dispatch_only_committed_own_outbox(client, monkeypatch, route, data):
    auth = client.post("/auth/bootstrap", json={
        "organization_name": "Email School", "organization_slug": "email-school",
        "full_name": "Owner", "email": "owner-email@example.com", "password": "test-email-owner-password",
    }).json()
    called = []

    def deliver(org_id, row_id):
        with SessionLocal() as db:
            row = db.get(NotificationOutbox, row_id)
            assert row is not None and row.organization_id == org_id
            assert "expires_at" in row.payload
        called.append((org_id, row_id))

    monkeypatch.setattr(notifications, "deliver_one", deliver)
    response = client.post(route, headers={
        "Authorization": f"Bearer {auth['access_token']}", "X-Organization-Id": auth["organization_id"],
    }, json=data)
    assert response.status_code == 201, response.text
    assert len(called) == 1 and called[0][0] == UUID(auth["organization_id"])


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Production row-lock guarantee requires PostgreSQL")
def test_competing_workers_do_not_deliver_locked_message_twice(smtp, monkeypatch):
    org_id, row_id = queued()
    entered, release = Event(), Event()
    errors = []
    original = smtp[1].send_message

    def slow(self, message):
        entered.set()
        assert release.wait(10)
        original(self, message)

    def first():
        try:
            notifications.deliver_one(org_id, row_id)
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(smtp[1], "send_message", slow)
    worker = Thread(target=first)
    worker.start()
    try:
        assert entered.wait(10)
        notifications.deliver_one(org_id, row_id)
    finally:
        release.set()
        worker.join(timeout=10)
    assert not worker.is_alive() and not errors
    assert len(smtp[0]) == 1
