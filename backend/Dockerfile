# ── Stage 1 : builder ──────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

COPY requirements.txt .

# Installe dans un prefix isolé — ne pollue pas l'image finale
RUN pip install --prefix=/install -r requirements.txt


# ── Stage 2 : runtime ──────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Utilisateur non-root dédié (uid 1000, sans home)
RUN groupadd --gid 1000 --system appgroup && \
    useradd --uid 1000 --system --gid appgroup --no-create-home appuser

WORKDIR /app

# Dépendances depuis le builder
COPY --from=builder /install /usr/local

# Code applicatif — le build context est ./backend (voir docker-compose.yml)
# donc le Dockerfile reçoit le contenu de backend/ à sa racine
COPY --chown=appuser:appgroup . .

# config.yaml monté en volume read-only en prod (docker-compose.yml)
# Le COPY ci-dessus ne copie pas config.yaml — il n'existe pas au build time
# (seul config.yaml.example est commité). Le volume prod l'injecte au runtime.

USER appuser

EXPOSE 8000

# Healthcheck via python — curl absent de python:3.12-slim
# IMPORTANT : ce HEALTHCHECK est surchargé par celui du docker-compose.yml
# (docker-compose a priorité). Cohérence garantie : les deux testent /health.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# exec form — SIGTERM atteint uvicorn directement (pas via shell)
# main:app car le CWD est /app et le module est /app/main.py
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
