import base64
import hashlib
import hmac
import time

from app.config import TURN_DOMAIN, TURN_SHARED_SECRET

# Standard coturn REST API credential scheme (RFC 5766 TURN + the
# widely-used time-limited-credential convention coturn implements via
# `use-auth-secret`) -- same scheme and same coturn instance telecom-assistant
# already runs. The secret itself never leaves this backend, only the
# derived, time-limited pair does.
DEFAULT_TTL_SECONDS = 3600


def is_enabled() -> bool:
    return bool(TURN_SHARED_SECRET and TURN_DOMAIN)


def generate_turn_credentials(ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict | None:
    if not is_enabled():
        return None

    username = str(int(time.time()) + ttl_seconds)
    digest = hmac.new(TURN_SHARED_SECRET.encode(), username.encode(), hashlib.sha1).digest()
    credential = base64.b64encode(digest).decode()

    return {
        "urls": [f"turns:{TURN_DOMAIN}:5349?transport=tcp"],
        "username": username,
        "credential": credential,
    }
