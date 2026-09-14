"""Arkesel's signed callbacks (SMS and Voice), verified exactly as Arkesel's signing guide specifies.

The guide comes from Arkesel support (https://arkesel.com/contact/). The signature is an
HMAC-SHA256 hex digest of "{timestamp}.{canonical JSON of the query
parameters}". Canonical JSON sorts keys at every depth, keeps list order,
leaves slashes unescaped and escapes non-ASCII as PHP's json_encode does
(ensure_ascii=True: never change it, or only non-ASCII payloads would fail).
The signature header holds "v1=<hex>", or two comma-separated values during a
secret rotation, and either may match. Comparison is constant-time, and a
timestamp more than 5 minutes from now is refused.

Arkesel does not sign USSD callbacks yet; see the USSD route for how those are
protected until it does.
"""

import hashlib
import hmac
import json
import time
from typing import Any

TIMESTAMP_HEADER = "X-Arkesel-Webhook-Timestamp"
SIGNATURE_HEADER = "X-Arkesel-Webhook-Signature"
ID_HEADER = "X-Arkesel-Webhook-Id"
MAX_AGE_SECONDS = 300


def sort_recursively(value: Any) -> Any:
    if isinstance(value, list):
        return [sort_recursively(item) for item in value]
    if isinstance(value, dict):
        return {key: sort_recursively(value[key]) for key in sorted(value.keys())}
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(sort_recursively(payload), separators=(",", ":"), ensure_ascii=True)


def extract_signatures(signature_header: str) -> list[str]:
    return [part.strip()[3:] for part in signature_header.split(",") if part.strip().startswith("v1=")]


def verify_webhook(
    query_params: dict[str, Any],
    timestamp_header: str,
    signature_header: str,
    webhook_secret: str,
    now: float | None = None,
) -> bool:
    """True only for a callback Arkesel signed with this secret in the last 5 minutes."""
    if not webhook_secret or not (timestamp_header.isascii() and timestamp_header.isdigit()):
        return False
    moment = time.time() if now is None else now
    if abs(int(moment) - int(timestamp_header)) > MAX_AGE_SECONDS:
        return False
    canonical_string = f"{timestamp_header}.{canonical_json(query_params)}"
    computed_signature = hmac.new(webhook_secret.encode("utf-8"), canonical_string.encode("utf-8"), hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(computed_signature, received) for received in extract_signatures(signature_header))
