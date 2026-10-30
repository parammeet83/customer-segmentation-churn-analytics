"""Stable pseudonymous customer keys.

``customer_key = "C-" + first 12 hex chars of HMAC-SHA256(secret, customer_id)``

The secret is read from ``CUSTOMERPULSE_PSEUDONYM_SECRET`` and never stored
with the outputs. Without the secret the mapping cannot be recomputed from a
known ID, but this is pseudonymisation, not anonymisation: behavioural
profiles can still be distinctive, so the public API exposes only aggregated
features.
"""

from __future__ import annotations

import hashlib
import hmac
import os

import pandas as pd

ENV_VAR = "CUSTOMERPULSE_PSEUDONYM_SECRET"
MIN_SECRET_LENGTH = 16


def get_secret() -> bytes:
    secret = os.environ.get(ENV_VAR, "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise RuntimeError(f"{ENV_VAR} must be set to a random value of at least {MIN_SECRET_LENGTH} characters")
    return secret.encode()


def customer_key(customer_id: str, secret: bytes) -> str:
    digest = hmac.new(secret, str(customer_id).encode(), hashlib.sha256).hexdigest()
    return f"C-{digest[:12]}"


def add_customer_keys(df: pd.DataFrame, secret: bytes, id_col: str = "customer_id") -> pd.DataFrame:
    keys = {cid: customer_key(cid, secret) for cid in df[id_col].unique()}
    if len(set(keys.values())) != len(keys):
        raise RuntimeError("Pseudonymous key collision; increase key length")
    out = df.copy()
    out["customer_key"] = out[id_col].map(keys)
    return out
