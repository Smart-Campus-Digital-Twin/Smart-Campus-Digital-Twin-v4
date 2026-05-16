from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def _fetch_jwks(keycloak_internal_url: str, realm: str, *, timeout_s: float = 5.0) -> dict:
    jwks_url = f"{keycloak_internal_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/certs"
    resp = requests.get(jwks_url, timeout=timeout_s)
    resp.raise_for_status()
    return resp.json()


def _jwks_to_pem_public_key(jwks: dict) -> str:
    keys = jwks.get("keys") or []
    rsa_keys = [k for k in keys if k.get("kty") == "RSA" and k.get("use") in (None, "sig")]
    if not rsa_keys:
        raise RuntimeError("No RSA signing keys found in JWKS")

    key = rsa_keys[0]
    n_b64 = key.get("n")
    e_b64 = key.get("e")
    if not n_b64 or not e_b64:
        raise RuntimeError("JWKS RSA key missing 'n' or 'e'")

    numbers = rsa.RSAPublicNumbers(
        e=int.from_bytes(_b64url_decode(e_b64), "big"),
        n=int.from_bytes(_b64url_decode(n_b64), "big"),
    )
    public_key = numbers.public_key()
    pem_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return pem_bytes.decode("utf-8").strip()


def _b64url_decode(data: str) -> bytes:
    import base64

    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _render_template(template_text: str, *, issuer: str, rsa_public_key_pem: str) -> str:
    if "__JWT_ISSUER__" not in template_text:
        raise RuntimeError("Template missing __JWT_ISSUER__ placeholder")
    if "__JWT_RSA_PUBLIC_KEY__" not in template_text:
        raise RuntimeError("Template missing __JWT_RSA_PUBLIC_KEY__ placeholder")

    out_lines: list[str] = []
    for line in template_text.splitlines(keepends=True):
        if "__JWT_RSA_PUBLIC_KEY__" in line:
            prefix = line.split("__JWT_RSA_PUBLIC_KEY__")[0]
            for pem_line in rsa_public_key_pem.splitlines():
                out_lines.append(prefix + pem_line + "\n")
            continue

        out_lines.append(line.replace("__JWT_ISSUER__", issuer))

    return "".join(out_lines)


def main() -> int:
    keycloak_internal_url = _require_env("KEYCLOAK_INTERNAL_URL")
    realm = _require_env("KEYCLOAK_REALM")
    issuer = _require_env("JWT_ISSUER")
    template_path = Path(_require_env("KONG_TEMPLATE_PATH"))
    out_path = Path(_require_env("KONG_OUT_PATH"))

    attempts = int(os.getenv("KEYCLOAK_JWKS_ATTEMPTS", "30"))
    sleep_s = float(os.getenv("KEYCLOAK_JWKS_SLEEP_S", "3"))

    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            jwks = _fetch_jwks(keycloak_internal_url, realm)
            pem = _jwks_to_pem_public_key(jwks)
            rendered = _render_template(template_path.read_text(encoding="utf-8"), issuer=issuer, rsa_public_key_pem=pem)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(rendered, encoding="utf-8")
            print(f"Wrote Kong declarative config: {out_path}")
            return 0
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            time.sleep(sleep_s)

    print(f"Failed to render Kong config after {attempts} attempts: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
