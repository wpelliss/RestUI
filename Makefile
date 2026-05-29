# Makefile — RestUI
# Cibles principales pour le cycle dev/déploiement sur Pi5.
# Prérequis : docker, docker compose (plugin v2), make.
# config.yaml vit à la racine du projet (monté en volume dans le container).
# backend/.env contient les credentials (jamais commité).

.DEFAULT_GOAL := help
.PHONY: help config dev build deploy logs restart stop test clean

# ── Variables ──────────────────────────────────────────────────────────────

COMPOSE        := docker compose
COMPOSE_PROD   := docker compose -f docker-compose.yml
SERVICE        := restui-backend
IMAGE          := restui/backend

# ── Aide ───────────────────────────────────────────────────────────────────

help:
	@echo ""
	@echo "  RestUI — commandes disponibles"
	@echo ""
	@echo "  make config    Initialise backend/.env et config.yaml depuis les exemples."
	@echo "                 Ne remplace jamais un fichier existant."
	@echo ""
	@echo "  make dev       Lance en mode développement (hot-reload, port 127.0.0.1:8000)."
	@echo "                 docker-compose.override.yml appliqué automatiquement."
	@echo "                 caddy_net créé localement si absent (bridge ordinaire)."
	@echo ""
	@echo "  make build     Build l'image Docker production (stage runtime, --no-cache)."
	@echo ""
	@echo "  make deploy    Build + relance en production (detached, port non exposé)."
	@echo "                 A exécuter sur le Pi5 après git pull."
	@echo "                 Prérequis : réseau caddy_net existant (créé par l'infra Pi5)."
	@echo ""
	@echo "  make logs      Suit les logs en temps réel (Ctrl+C pour quitter)."
	@echo ""
	@echo "  make restart   Redémarre le service sans rebuild."
	@echo "                 Utile après modification de config.yaml."
	@echo ""
	@echo "  make stop      Arrête tous les services."
	@echo ""
	@echo "  make test      Lance les smoke tests (pytest dans le venv local)."
	@echo ""
	@echo "  make clean     Supprime les images et volumes non utilisés."
	@echo ""

# ── Config initiale ────────────────────────────────────────────────────────

config:
	@if [ ! -f backend/.env ]; then \
		cp backend/.env.example backend/.env; \
		echo "  backend/.env cree — renseigner API_USERNAME et API_PASSWORD."; \
	else \
		echo "  backend/.env existe deja, non modifie."; \
	fi
	@if [ ! -f config.yaml ]; then \
		cp backend/config.yaml.example config.yaml; \
		echo "  config.yaml cree depuis config.yaml.example — adapter les endpoints."; \
	else \
		echo "  config.yaml existe deja, non modifie."; \
	fi

# ── Développement ──────────────────────────────────────────────────────────

dev: config
	$(COMPOSE) up

# ── Build ──────────────────────────────────────────────────────────────────

build:
	$(COMPOSE_PROD) build --no-cache $(SERVICE)

# ── Déploiement production ─────────────────────────────────────────────────

deploy: config
	$(COMPOSE_PROD) build $(SERVICE)
	$(COMPOSE_PROD) up -d --remove-orphans
	@echo ""
	@echo "  Deploiement lance. Health check dans 20s..."
	@sleep 20
	@$(COMPOSE_PROD) ps

# ── Logs ───────────────────────────────────────────────────────────────────

logs:
	$(COMPOSE) logs -f --tail=100 $(SERVICE)

# ── Restart ────────────────────────────────────────────────────────────────
# Utile après modif config.yaml (pas de hot-reload sur ce fichier)

restart:
	$(COMPOSE_PROD) restart $(SERVICE)
	@echo "  Service redемarre. En attente du health check (10s)..."
	@sleep 10
	@$(COMPOSE_PROD) ps $(SERVICE)

# ── Stop ───────────────────────────────────────────────────────────────────

stop:
	$(COMPOSE) down

# ── Tests ──────────────────────────────────────────────────────────────────
# Les tests importent depuis backend/ avec sys.path ajusté dans test_smoke.py.
# python3 peut s'appeler python sur certains systemes — adapter si besoin.

test:
	@if [ ! -d .venv ]; then \
		echo "  Creation du venv local..."; \
		python3 -m venv .venv || python -m venv .venv; \
		.venv/bin/pip install -q -r backend/requirements.txt pytest 2>/dev/null \
		|| .venv/Scripts/pip install -q -r backend/requirements.txt pytest; \
	fi
	.venv/bin/pytest backend/tests/ -v 2>/dev/null \
	|| .venv/Scripts/pytest backend/tests/ -v

# ── Nettoyage ──────────────────────────────────────────────────────────────

clean:
	docker image prune -f
	docker volume prune -f
	@echo "  Images et volumes non utilises supprimes."
