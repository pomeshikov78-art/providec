"""Безопасность ядра: заголовки, rate limiting (API Gateway), крипто-абстракция.

ТЗ п.9 / Приложение 7 (ФСТЭК, вариант Б — класс 1Б):
  * SECURITY_HEADERS: CSP, X-Frame-Options, HSTS (вариант А), nosniff;
  * RateLimiter: скользящее окно на субъект (in-memory для одиночного узла;
    в кластере — Redis INCR, адаптер подключается по конфигурации);
  * CryptoProvider: абстракция криптопровайдера. Dev-профиль — hashlib/JWT HS256;
    prod вариант Б — СКЗИ с ГОСТ Р 34.12-2015 (Магма/Кузнечик) и ЭП ГОСТ Р 34.10-2012
    через сертифицированный крипто-шлюз (КриптоПро/КриптОН): точки расширения
    sign()/verify()/encrypt()/decrypt() помечены NotImplemented до подключения СКЗИ.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from ..config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp: Response = await call_next(request)
        if settings().security_headers:
            resp.headers.setdefault("X-Content-Type-Options", "nosniff")
            resp.headers.setdefault("X-Frame-Options", "DENY")
            resp.headers.setdefault("Referrer-Policy", "no-referrer")
            resp.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
            if settings().variant == "network":
                resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return resp


class RateLimiter:
    """Скользящее окно: N запросов/минуту на субъект (login или IP)."""

    def __init__(self) -> None:
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        limit = settings().rate_limit_per_minute
        now = time.monotonic()
        with self._lock:
            dq = self._hits[key]
            while dq and now - dq[0] > 60.0:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/api/"):
            auth = request.headers.get("authorization", "")
            key = auth[-40:] if auth else (request.client.host if request.client else "anon")
            if not limiter.allow(key):
                return JSONResponse({"detail": "Rate limit exceeded (API Gateway, ТЗ п.4.4.1)"}, status_code=429)
        return await call_next(request)


limiter = RateLimiter()


class CryptoProvider:
    """Абстракция криптопровайдера (dev: hashlib; prod вариант Б: СКЗИ ГОСТ)."""

    name = "dev-hashlib"

    def digest(self, data: bytes) -> bytes:
        import hashlib
        return hashlib.sha256(data).digest()

    def sign(self, data: bytes) -> bytes:
        raise NotImplementedError("Требуется СКЗИ: ЭП ГОСТ Р 34.10-2012 (КриптоПро/КриптОН)")

    def verify(self, data: bytes, signature: bytes) -> bool:
        raise NotImplementedError("Требуется СКЗИ: ЭП ГОСТ Р 34.10-2012")

    def encrypt(self, data: bytes) -> bytes:
        raise NotImplementedError("Требуется СКЗИ: ГОСТ Р 34.12-2015 (Магма/Кузнечик)")

    def decrypt(self, data: bytes) -> bytes:
        raise NotImplementedError("Требуется СКЗИ: ГОСТ Р 34.12-2015")


crypto = CryptoProvider()
