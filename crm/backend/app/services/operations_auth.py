from __future__ import annotations

import jwt
from jwt import PyJWKClient

from app.core.config import settings


GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
GITHUB_OIDC_JWKS = "https://token.actions.githubusercontent.com/.well-known/jwks"

_jwks_client = PyJWKClient(GITHUB_OIDC_JWKS, cache_keys=True)


class MaintenanceIdentityError(ValueError):
    pass


def verify_github_actions_token(token: str) -> dict:
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.maintenance_oidc_audience,
            issuer=GITHUB_OIDC_ISSUER,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        raise MaintenanceIdentityError("Invalid GitHub Actions identity token") from exc

    if claims.get("repository") != settings.maintenance_github_repository:
        raise MaintenanceIdentityError("Unexpected GitHub repository")
    if claims.get("ref") != settings.maintenance_github_ref:
        raise MaintenanceIdentityError("Unexpected GitHub ref")
    if claims.get("event_name") not in {"schedule", "workflow_dispatch"}:
        raise MaintenanceIdentityError("Unsupported GitHub Actions event")

    workflow_ref = str(claims.get("workflow_ref") or "")
    expected_prefix = (
        f"{settings.maintenance_github_repository}/"
        ".github/workflows/crm-maintenance.yml@"
        f"{settings.maintenance_github_ref}"
    )
    if workflow_ref != expected_prefix:
        raise MaintenanceIdentityError("Unexpected GitHub workflow")

    return claims
