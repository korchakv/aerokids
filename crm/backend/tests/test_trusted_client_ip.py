from app.core.config import settings


def test_login_ip_limit_uses_cloudflare_ip_not_client_forwarded_for(client, monkeypatch):
    monkeypatch.setattr(settings, "auth_login_ip_limit", 1)
    monkeypatch.setattr(settings, "auth_login_email_limit", 100)
    bootstrap = client.post(
        "/auth/bootstrap",
        json={
            "organization_name": "AeroKiDS",
            "organization_slug": "aerokids-security",
            "full_name": "Owner User",
            "email": "owner@aerokids.test",
            "password": "very-secure-password",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text

    first = client.post(
        "/auth/login",
        json={"email": "owner@aerokids.test", "password": "wrong-password"},
        headers={
            "CF-Connecting-IP": "198.51.100.10",
            "X-Forwarded-For": "203.0.113.10",
        },
    )
    second = client.post(
        "/auth/login",
        json={"email": "owner@aerokids.test", "password": "wrong-password"},
        headers={
            "CF-Connecting-IP": "198.51.100.10",
            "X-Forwarded-For": "203.0.113.11",
        },
    )
    assert first.status_code == 401
    assert second.status_code == 429


def test_public_intake_ip_limit_uses_cloudflare_ip_not_client_forwarded_for(client, monkeypatch):
    monkeypatch.setattr(settings, "public_intake_ip_limit", 1)
    monkeypatch.setattr(settings, "public_intake_phone_limit", 100)
    organization = client.post(
        "/organizations",
        json={"name": "AeroKiDS", "slug": "aerokids-public-security"},
    )
    assert organization.status_code == 201, organization.text

    first = client.post(
        "/public/intake/aerokids-public-security",
        json={
            "child_first_name": "Марта",
            "child_age": 9,
            "contact_name": "Оксана",
            "phone": "0671234567",
        },
        headers={
            "CF-Connecting-IP": "198.51.100.20",
            "X-Forwarded-For": "203.0.113.20",
        },
    )
    second = client.post(
        "/public/intake/aerokids-public-security",
        json={
            "child_first_name": "Софія",
            "child_age": 10,
            "contact_name": "Оксана",
            "phone": "0671234568",
        },
        headers={
            "CF-Connecting-IP": "198.51.100.20",
            "X-Forwarded-For": "203.0.113.21",
        },
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 429
