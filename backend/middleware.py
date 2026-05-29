"""
RestUI — Security headers middleware FastAPI
Utilisé en développement local sans Caddy.
En production, ces headers sont posés par Caddy (Caddyfile snippet security_headers).
Inclure ce middleware en dev via : app.add_middleware(SecurityHeadersMiddleware)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


# CSP identique au Caddyfile — single source of truth à terme via config.yaml
_CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.tailwindcss.com https://unpkg.com 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

_SECURITY_HEADERS: dict[str, str] = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    # HSTS seulement en production (HTTPS) — Caddy le pose en prod, pas ce middleware
    # "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Content-Security-Policy": _CSP,
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware de sécurité pour développement local (sans Caddy).
    En production : Caddy pose ces headers — ce middleware peut rester actif
    sans conflit (idempotent sur les valeurs identiques).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)

        for header, value in _SECURITY_HEADERS.items():
            # Ne pas écraser si déjà posé par Caddy (défense en profondeur harmless)
            if header not in response.headers:
                response.headers[header] = value

        # Supprimer le header server FastAPI/uvicorn
        response.headers.pop("server", None)

        return response
