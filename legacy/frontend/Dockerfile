# ============================================================
# RestUI — Frontend Dockerfile
# Multi-stage : build Node 20 → runtime Node 20-slim
# SSR obligatoire : toutes les pages ont prerender: false.
# CMD : entry point généré par @astrojs/node (adapter standalone).
# ============================================================

# ---- Build stage ----
FROM node:20-alpine AS builder

WORKDIR /app

# Copie des fichiers de dépendances en premier (cache layer Docker)
COPY package.json package-lock.json* ./
RUN npm ci --prefer-offline

# Copie du source et build Astro SSR
COPY . .

# BACKEND_URL n'est pas nécessaire au BUILD (pas de static pre-render).
# Elle est injectée à l'EXÉCUTION via Docker Compose env_file ou environment.
RUN npm run build

# ---- Runtime stage ----
FROM node:20-alpine AS runtime

WORKDIR /app

# Utilisateur non-root — sécurité minimale
RUN addgroup -S restui && adduser -S restui -G restui

# Copie uniquement le dist et les node_modules nécessaires au runtime
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

USER restui

EXPOSE 4321

# BACKEND_URL doit être fournie par Docker Compose au démarrage.
# En prod Docker : http://restui-backend:8000 (nom de service docker-compose.yml)
# En dev local  : http://localhost:8000
ENV HOST=0.0.0.0
ENV PORT=4321

# HEALTHCHECK — utilisé par Docker et potentiellement par Caddy
HEALTHCHECK --interval=30s --timeout=10s --retries=3 --start-period=20s \
  CMD wget -qO- http://localhost:4321/ || exit 1

# Entry point généré par @astrojs/node adapter standalone
CMD ["node", "./dist/server/entry.mjs"]
