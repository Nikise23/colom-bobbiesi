"""Límite de intentos de login por IP (en memoria; suficiente para una instancia en Render)."""

from __future__ import annotations

import os
import time
from collections import defaultdict

from flask import Request

_failed_attempts: dict[str, list[float]] = defaultdict(list)
_lockouts_until: dict[str, float] = {}


def _max_attempts() -> int:
    try:
        return max(1, int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5")))
    except ValueError:
        return 5


def _lockout_seconds() -> int:
    try:
        minutes = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
        return max(1, minutes) * 60
    except ValueError:
        return 15 * 60


def client_ip(request: Request) -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return (request.remote_addr or "unknown").strip()


def is_login_blocked(ip: str) -> tuple[bool, int]:
    """Devuelve (bloqueado, segundos_restantes)."""
    now = time.time()
    locked_until = _lockouts_until.get(ip)
    if locked_until and now < locked_until:
        return True, int(locked_until - now) + 1
    if locked_until and now >= locked_until:
        _lockouts_until.pop(ip, None)
        _failed_attempts.pop(ip, None)
    return False, 0


def record_failed_login(ip: str) -> tuple[bool, int]:
    """Registra un intento fallido. Devuelve si quedó bloqueado y segundos de espera."""
    now = time.time()
    window = _lockout_seconds()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < window]
    attempts.append(now)
    _failed_attempts[ip] = attempts

    if len(attempts) >= _max_attempts():
        _lockouts_until[ip] = now + window
        return True, window
    return False, 0


def clear_login_attempts(ip: str) -> None:
    _failed_attempts.pop(ip, None)
    _lockouts_until.pop(ip, None)


def reset_all() -> None:
    """Solo para tests."""
    _failed_attempts.clear()
    _lockouts_until.clear()
