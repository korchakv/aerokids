from starlette.requests import Request

from app.api.router import _trusted_client_ip


def _request(headers: dict[str, str], client: tuple[str, int] = ("testclient", 50000)) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
        "client": client,
        "server": ("testserver", 80),
        "scheme": "http",
    })


def test_trusted_client_ip_prefers_cloudflare_over_forged_forwarded_for():
    request = _request({
        "CF-Connecting-IP": "198.51.100.10",
        "X-Forwarded-For": "203.0.113.10",
    })

    assert _trusted_client_ip(request) == "198.51.100.10"


def test_trusted_client_ip_uses_fallback_if_cloudflare_value_is_invalid():
    request = _request({
        "CF-Connecting-IP": "not-an-ip",
        "X-Forwarded-For": "203.0.113.10",
    }, client=("192.0.2.20", 50000))

    assert _trusted_client_ip(request) == "192.0.2.20"
