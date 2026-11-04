# ==============================
# Standard Library
# ==============================
import time
import threading

# ==============================
# Third-Party Libraries
# ==============================
from fastapi import HTTPException

# ==============================
# Internal Modules
# ==============================
from core.config import settings

# ==========================================================================
# Failed login limit for username + password login.
# After LOGIN_MAX_FAILED_ATTEMPTS wrong passwords in a row, the username is
# blocked for LOGIN_LOCKOUT_MINUTES, even if the next password is correct.
#
# The counters are kept in memory: they are per server process and are
# cleared on restart. That fits password login being used on local only.
# ==========================================================================

_attempts = {}  # username -> {"count": failed attempts, "last": time of the last one}
_lock = threading.Lock()


def _key(username: str) -> str:
    return (username or "").strip().lower()


def _lockout_seconds() -> int:
    return settings.LOGIN_LOCKOUT_MINUTES * 60


# Raise 429 if this username is currently blocked
def check_login_allowed(username: str):
    with _lock:
        entry = _attempts.get(_key(username))
        if not entry:
            return

        waited = time.time() - entry["last"]
        if waited >= _lockout_seconds():
            # block (or old failures) expired → start again from zero
            del _attempts[_key(username)]
            return

        if entry["count"] >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            minutes_left = int((_lockout_seconds() - waited) // 60) + 1
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed login attempts. Please try again in {minutes_left} minute(s)."
            )


# Count one wrong username / password
def record_failed_login(username: str):
    now = time.time()
    with _lock:
        # forget expired entries so the list cannot grow forever
        for name in [n for n, e in _attempts.items() if now - e["last"] >= _lockout_seconds()]:
            del _attempts[name]

        entry = _attempts.setdefault(_key(username), {"count": 0, "last": now})
        entry["count"] += 1
        entry["last"] = now


# Successful login → forget earlier failures
def clear_failed_logins(username: str):
    with _lock:
        _attempts.pop(_key(username), None)
