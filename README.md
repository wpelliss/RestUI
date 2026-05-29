# RestUI

Proxy HTTP vers API REST qui affiche les données JSON sous forme de tableau filtrable, dans un dashboard admin propre. Configuration déclarative par endpoint dans `config.yaml` — ajouter une vue revient à ajouter un bloc YAML, zéro code. Réécriture de la version PHP 2019 (credentials hardcodés, XSS triple, filtres GET non sanitisés).

**Stack :** FastAPI 0.115 (Python 3.12) · Jinja2 · HTMX · Tailwind CSS (CDN) · Docker Compose · Caddy

---

## Quick start

```bash
# 1. Cloner et initialiser la config
git clone <repo> restui && cd restui
make config
# → crée backend/.env et config.yaml depuis les exemples

# 2. Renseigner les credentials upstream dans backend/.env
#    Éditer : API_USERNAME=... API_PASSWORD=...

# 3. Déclarer les endpoints dans config.yaml (voir section Configuration)

# 4. Lancer en mode développement
make dev
# → http://127.0.0.1:8000

# 5. Ouvrir http://127.0.0.1:8000
```

---

## Configuration

### `config.yaml`

Fichier à la racine du projet. Monté en volume read-only dans le container. Un restart est nécessaire après modification (`make restart`).

```yaml
endpoints:

  - name: users                      # slug URL : /users — identifiant unique
    label: Utilisateurs               # libellé affiché dans le sidebar
    url: https://api.example.com/v1/users
    parent_field: users               # clé JSON contenant le tableau
                                      # omettre si la réponse est directement []

    columns:
      - key: id
        label: ID
        filterable: false
        hidden: true                  # présent dans les données, masqué dans la table

      - key: username
        label: Nom d'utilisateur
        filterable: true              # ?username=alice → filtre substring insensible à la casse

      - key: profile.department       # dot-notation : {"profile": {"department": "..."}}
        label: Département
        filterable: true

  - name: terminals
    label: Terminaux
    url: https://api.example.com/v1/terminals
    # parent_field absent → réponse directement un tableau JSON

    columns:
      - key: serial_number
        label: Numéro de série
        filterable: true
      - key: location.city
        label: Ville
        filterable: true
```

**Référence des clés :**

| Clé | Type | Obligatoire | Description |
|-----|------|-------------|-------------|
| `name` | string | oui | Identifiant unique, utilisé comme slug URL (`/{name}`) |
| `label` | string | oui | Libellé affiché dans le sidebar |
| `url` | string | oui | URL complète de l'API upstream. Basic Auth ajouté automatiquement. |
| `parent_field` | string | non | Clé JSON contenant le tableau si la réponse est un objet. |
| `columns[].key` | string | oui | Chemin dot-notation (`address.city` pour `{"address": {"city": "..."}}`) |
| `columns[].label` | string | oui | En-tête de colonne |
| `columns[].filterable` | bool | non (défaut: false) | Expose ce champ comme filtre URL (`?key=valeur`) |
| `columns[].hidden` | bool | non (défaut: false) | Inclut dans les données, masqué dans la table |

---

### `backend/.env`

Secrets uniquement. Ce fichier ne doit jamais être commité (`.gitignore` l'exclut).

```dotenv
# Credentials HTTP Basic Auth pour l'API upstream — obligatoires
API_USERNAME=your_user
API_PASSWORD=your_password

# Timeouts httpx (optionnel — valeurs par défaut)
# UPSTREAM_TIMEOUT_CONNECT=5.0
# UPSTREAM_TIMEOUT_READ=30.0

# Chemin vers config.yaml (optionnel — défaut: "config.yaml")
# CONFIG_YAML_PATH=config.yaml

# Mode debug : active /docs FastAPI. Ne jamais mettre true en prod.
# DEBUG=false

# Niveau de log : DEBUG, INFO, WARNING, ERROR
# LOG_LEVEL=INFO
```

`API_USERNAME` et `API_PASSWORD` sont les seules variables obligatoires. Le démarrage échoue si elles sont absentes ou vides.

---

## Architecture

```
               Cloudflare Tunnel
                      │
               ┌──────▼──────┐
               │    Caddy    │  restui.wilpel.dev
               │  (caddy_net)│  TLS, security headers, Basic Auth (optionnel)
               └──────┬──────┘
                      │ tout le trafic
               ┌──────▼──────────────────┐
               │   FastAPI + Jinja2      │  :8000
               │   HTMX pour partials    │
               └──────┬──────────────────┘
                      │ httpx + Basic Auth
                      ▼
               API upstream (HTTP REST JSON)
```

**Flux d'une requête :**
1. Caddy reçoit la requête sur `restui.wilpel.dev` → applique security headers → forward vers backend:8000
2. FastAPI route vers `/{slug}` → lit config.yaml → appelle l'API upstream via httpx
3. La réponse JSON est projetée sur les colonnes déclarées, filtrée par les query params
4. Jinja2 rend la page HTML avec la table
5. HTMX gère les mises à jour partielles sur changement de filtre (sans rechargement complet)
6. L'URL reflète l'état des filtres actifs — shareable par copier-coller

**Sécurité par design :**
- Credentials upstream lus depuis `.env` via pydantic-settings — jamais dans le code
- Seules les colonnes `filterable: true` sont filtrables — pas d'injection arbitraire depuis l'URL
- Jinja2 auto-escape actif — XSS structurellement impossible
- Auth utilisateur déléguée à Caddy — l'app ne voit jamais de credentials utilisateur
- `/docs` FastAPI désactivé sauf `DEBUG=true`

---

## Structure du projet

```
restui/
├── backend/
│   ├── main.py               # Routes FastAPI (HTML Jinja2 + JSON API + HTMX partials)
│   ├── config.py             # pydantic-settings (.env) + modèles YAML
│   ├── proxy.py              # Fonctions pures : resolve_nested, extract_rows, apply_filters
│   ├── middleware.py         # Security headers (dev local sans Caddy)
│   ├── templates/
│   │   ├── base.html         # Layout commun (Tailwind CDN, HTMX CDN, sidebar)
│   │   ├── table.html        # Table + filtres URL-shareables
│   │   ├── rows.html         # Fragment HTMX (<tbody> uniquement)
│   │   └── error.html        # Page d'erreur
│   ├── tests/
│   │   └── test_smoke.py     # Smoke tests pytest (fonctions pures, sans réseau)
│   ├── config.yaml.example   # Template config (commité)
│   ├── .env.example          # Template secrets (commité)
│   ├── requirements.txt
│   └── Dockerfile
├── config.yaml               # Déclaration endpoints (copier depuis config.yaml.example)
├── Caddyfile                 # Configuration Caddy production
├── docker-compose.yml        # Service restui-backend sur caddy_net
├── docker-compose.override.yml  # Dev : hot-reload, port 127.0.0.1:8000 exposé
├── Makefile
├── .env.example              # Template — copier vers backend/.env
├── .gitignore
└── legacy/                   # Code PHP 2019 archivé (référence historique)
```

---

## Déploiement Pi5

Prérequis : réseau Docker `caddy_net` existant.

```bash
# Sur le Pi5 — depuis le répertoire du projet

# 1. Récupérer les derniers changements
git pull

# 2. Initialiser la config si premier déploiement
make config
# Puis éditer backend/.env et config.yaml

# 3. Construire et démarrer
make deploy
# → build image production, docker compose up -d, health check 20s

# 4. Vérifier
make logs
# → "config.yaml chargé — N endpoint(s)"

# 5. Ajouter l'entrée dans le Caddyfile du Pi5 (voir Caddyfile du projet)
#    puis reload Caddy :
docker exec <caddy_container> caddy reload --config /etc/caddy/Caddyfile
```

**Après modification de `config.yaml` uniquement :**
```bash
make restart   # Redémarre sans rebuild (suffit pour recharger la config)
```

**Commandes disponibles :**
```bash
make config    # Initialise backend/.env et config.yaml depuis les exemples
make dev       # Développement avec hot-reload
make build     # Build image production
make deploy    # Build + démarrage production
make logs      # Logs temps réel
make restart   # Redémarre le backend
make stop      # Arrêt propre
make test      # Smoke tests pytest
make clean     # Prune images/volumes inutilisés
```

---

## Développement local

```bash
# Avec Docker (recommandé)
make dev
# Backend : http://127.0.0.1:8000
# /docs disponible si DEBUG=true dans backend/.env

# Sans Docker — backend seul
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows : .venv\Scripts\activate
pip install -r requirements.txt
# config.yaml doit exister à la racine du projet
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

**Tests :**
```bash
make test
# Crée un venv local, installe pytest, lance backend/tests/test_smoke.py
# Tests unitaires sans infra — pas d'appel réseau
```

---

## Routes

| Route | Description |
|-------|-------------|
| `GET /health` | Health check Docker/Caddy — `{"status": "ok"}` |
| `GET /` | Redirect vers le premier endpoint configuré |
| `GET /{slug}` | Page complète avec table et filtres |
| `GET /{slug}/rows` | Fragment HTMX — tbody mis à jour (filtres URL) |
| `GET /api/endpoints` | Liste JSON des endpoints (métadonnées, sans URL ni credentials) |
| `GET /api/data?endpoint=<name>[&filter=val]` | Données JSON filtrées |

---

## Licence

MIT — Copyright 2026 Wilfried Pellissard
