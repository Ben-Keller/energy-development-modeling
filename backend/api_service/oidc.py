"""OIDC JWT validation helper (plan 2.2).

Validates Bearer tokens against the configured Entra ID tenant's OIDC
discovery endpoint. The function is import-guarded by users.py so local
dev (which uses the test_header auth mode) does not require
azure-identity or PyJWT at import time.

The OIDC validation flow is:
  1. Fetch the discovery document at {EDIM_ENTRA_TENANT_ID}/.well-known/openid-configuration
  2. Fetch the JWKS at discovery.jwks_uri
  3. For each request:
     - Decode the JWT header to find the key id (kid)
     - Locate the matching JWK and verify the RS256 signature
     - Validate iss, aud, exp, nbf claims

Real staging/prod will exercise this path. Local dev should set
EDIM_AUTH_MODE=test_header and this module will never be called.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


_TENANT_ID_ENV = "EDIM_ENTRA_TENANT_ID"
_API_CLIENT_ID_ENV = "EDIM_ENTRA_API_CLIENT_ID"
_API_AUDIENCE_ENV = "EDIM_ENTRA_API_AUDIENCE"


async def validate_bearer_token(token: str) -> dict[str, Any]:
    """Validate a Bearer token and return the decoded claims.

    Raises fastapi.HTTPException(401) on any failure. Never returns partial
    results.
    """
    from fastapi import HTTPException, status as http_status

    tenant_id = os.getenv(_TENANT_ID_ENV, "").strip()
    audience = os.getenv(_API_AUDIENCE_ENV) or os.getenv(_API_CLIENT_ID_ENV, "").strip()
    if not tenant_id or not audience:
        logger.error("OIDC misconfigured: missing tenant_id or audience env vars")
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="OIDC not configured.")

    discovery_url = f"https://login.microsoftonline.com/{tenant_id}/v2.0/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            discovery = (await client.get(discovery_url)).raise_for_status().json()
            jwks_uri = discovery["jwks_uri"]
            jwks = (await client.get(jwks_uri)).raise_for_status().json()
    except Exception as exc:
        logger.warning("OIDC discovery failed: %s", exc)
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="OIDC discovery failed.")

    try:
        import jwt  # PyJWT
        from jwt import PyJWKClient
    except ImportError:
        logger.error("PyJWT not installed; cannot validate OIDC tokens.")
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="OIDC validator unavailable.")

    jwks_client = PyJWKClient(jwks_uri, cache_keys=True, lifespan=300)
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["exp", "iat", "iss", "aud"]},
        )
    except Exception as exc:
        logger.info("JWT validation failed: %s", exc)
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token.")

    expected_iss = f"https://login.microsoftonline.com/{tenant_id}/v2.0"
    if claims.get("iss") != expected_iss:
        raise HTTPException(status_code=http_status.HTTP_401_UNAUTHORIZED, detail="Token issuer mismatch.")

    return claims
