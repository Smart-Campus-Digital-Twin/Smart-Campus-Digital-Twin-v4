"""
JWT validation — Keycloak RS256 primary, HS256 local-dev fallback.

PRODUCTION (set KEYCLOAK_JWKS_URL):
  - Fetches public keys from Keycloak JWKS endpoint on first use.
  - Keys cached for JWKS_CACHE_TTL_S seconds (default 300).
  - On unknown `kid`, cache is invalidated and re-fetched once (key rotation).
  - Verifies: signature, exp, iss (if KEYCLOAK_ISSUER set), aud.
  - Reads building UUIDs from the claim named KEYCLOAK_BUILDINGS_CLAIM.

LOCAL DEV (KEYCLOAK_JWKS_URL empty, JWT_SECRET set):
  - Falls back to HS256 with the shared secret.
  - Validates same claim shape.

Token claim contract (configure as custom attribute in Keycloak client mapper):
  {
    "sub":       "<keycloak-user-uuid>",
    "buildings": ["<building-uuid>", ...],   ← configurable claim name
    "iat":       <epoch>,
    "exp":       <epoch>
  }
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwk, jwt
from jose.backends import RSAKey

from api.core.config import settings

logger = logging.getLogger("api.security")

_bearer = HTTPBearer(auto_error=True)

# ---------------------------------------------------------------------------
# JWKS cache
# ---------------------------------------------------------------------------

class _JwksCache:
    """Thread-safe async JWKS cache with TTL and rotation support."""

    def __init__(self) -> None:
        self._keys: dict[str, RSAKey] = {}   # kid → RSAKey
        self._fetched_at: float = 0.0
        self._lock = asyncio.Lock()

    def _expired(self) -> bool:
        return (time.monotonic() - self._fetched_at) > settings.jwks_cache_ttl_s

    async def _fetch(self) -> None:
        """Pull JWKS from Keycloak and parse RSA keys by kid."""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(settings.keycloak_jwks_url)
            resp.raise_for_status()
            data = resp.json()

        self._keys = {
            k["kid"]: jwk.construct(k)
            for k in data.get("keys", [])
            if k.get("use") == "sig"
        }
        self._fetched_at = time.monotonic()
        logger.info("JWKS refreshed — %d signing key(s) loaded", len(self._keys))

    async def get_key(self, kid: str | None, *, force_refresh: bool = False) -> RSAKey | None:
        """Return the RSA key for *kid*, refreshing cache if needed."""
        async with self._lock:
            if force_refresh or self._expired():
                await self._fetch()
        return self._keys.get(kid or "")  # type: ignore[return-value]


_jwks_cache = _JwksCache()


# ---------------------------------------------------------------------------
# Token claims container
# ---------------------------------------------------------------------------

class TokenClaims:
    """Validated, decoded JWT payload — normalised for downstream use."""

    __slots__ = ("sub", "buildings", "exp", "iat")

    def __init__(self, sub: str, buildings: list[str], exp: int, iat: int) -> None:
        self.sub = sub
        self.buildings: list[str] = buildings
        self.exp = exp
        self.iat = iat

    def can_access(self, building_id: str | UUID) -> bool:
        """Return True if token grants access to *building_id*."""
        return str(building_id) in self.buildings


# ---------------------------------------------------------------------------
# Internal decode helpers
# ---------------------------------------------------------------------------

def _extract_claims(payload: dict) -> TokenClaims:
    buildings = payload.get(settings.keycloak_buildings_claim, [])
    if not isinstance(buildings, list):
        raise ValueError("buildings claim is not a list")
    return TokenClaims(
        sub=payload["sub"],
        buildings=[str(b) for b in buildings],
        exp=int(payload["exp"]),
        iat=int(payload["iat"]),
    )


async def _decode_keycloak(token: str) -> TokenClaims:
    """RS256 path — verifies against Keycloak JWKS."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise ValueError(f"Malformed token header: {exc}") from exc

    kid = header.get("kid")
    key = await _jwks_cache.get_key(kid)

    if key is None:
        # kid not in cache — might be a rotated key; try once after refresh
        key = await _jwks_cache.get_key(kid, force_refresh=True)

    if key is None:
        raise ValueError(f"Unknown kid '{kid}' — token rejected")

    options: dict = {"require": ["sub", "exp", "iat"]}
    decode_kwargs: dict = {
        "algorithms": ["RS256"],
        "options": options,
    }
    if settings.keycloak_issuer:
        decode_kwargs["issuer"] = settings.keycloak_issuer
    if settings.keycloak_audience:
        decode_kwargs["audience"] = settings.keycloak_audience

    try:
        payload = jwt.decode(token, key, **decode_kwargs)
    except ExpiredSignatureError:
        raise ValueError("Token expired") from None
    except JWTError as exc:
        raise ValueError(str(exc)) from exc

    return _extract_claims(payload)


def _decode_hs256(token: str) -> TokenClaims:
    """HS256 fallback — local dev only."""
    if not settings.jwt_secret or len(settings.jwt_secret) < 32:
        raise ValueError("JWT_SECRET not configured (min 32 chars) and KEYCLOAK_JWKS_URL is empty")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp", "iat"]},
        )
    except ExpiredSignatureError:
        raise ValueError("Token expired") from None
    except JWTError as exc:
        raise ValueError(str(exc)) from exc
    return _extract_claims(payload)


async def _decode(token: str) -> TokenClaims:
    """Route to Keycloak or HS256 based on configuration."""
    if settings.keycloak_jwks_url:
        return await _decode_keycloak(token)
    return _decode_hs256(token)


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> TokenClaims:
    """
    Decode and validate a Bearer JWT (REST endpoints).

    Raises:
        401 – missing / malformed / expired token
    """
    try:
        return await _decode(credentials.credentials)
    except ValueError as exc:
        logger.debug("JWT validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def assert_building_access(claims: TokenClaims, building_id: UUID | str) -> None:
    """
    Inline 403 guard — call inside endpoint body after get_current_user.

    Raises:
        403 – building_id not in token.buildings
    """
    if not claims.can_access(building_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This building is not in your token claims",
        )


# ---------------------------------------------------------------------------
# WebSocket token validation (query-param path — browsers can't set WS headers)
# ---------------------------------------------------------------------------

async def validate_ws_token(token: str) -> TokenClaims:
    """
    Async decode for the WebSocket handshake.

    Call before accepting the WebSocket upgrade.
    Raises ValueError on any failure so the caller can close with code 4001.
    """
    return await _decode(token)


# ---------------------------------------------------------------------------
# Startup validation
# ---------------------------------------------------------------------------

def verify_auth_config() -> None:
    """
    Called at app startup — warns if neither Keycloak nor HS256 is configured.

    Does NOT raise: public endpoints (/health, /campus/zones) still work.
    Protected endpoints will return 401/500 until auth is configured.
    """
    if settings.keycloak_jwks_url:
        logger.info("Auth mode: Keycloak JWKS (%s)", settings.keycloak_jwks_url)
    elif settings.jwt_secret and len(settings.jwt_secret) >= 32:
        logger.info("Auth mode: HS256 dev fallback")
    else:
        logger.warning(
            "AUTH NOT CONFIGURED — protected endpoints will fail. "
            "Set KEYCLOAK_JWKS_URL (prod) or JWT_SECRET≥32 chars (dev) in env/api.env"
        )
