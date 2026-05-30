"""
RestUI — backend FastAPI + Jinja2 + HTMX.

Routes exposées :
  GET /health              → health check Docker/Caddy
  GET /                    → redirect vers le premier endpoint configuré
  GET /{slug}              → page complète (layout + table + filtres URL-shareables)
  GET /{slug}/rows         → fragment HTMX (<tbody> filtré uniquement)
  GET /api/endpoints       → liste JSON des endpoints (disponible pour intégration externe)
  GET /api/data            → données JSON filtrées (disponible pour intégration externe)

Auth : déléguée à Caddy (Basic Auth). Cette app ne voit jamais de credentials
       utilisateur et ne doit jamais être exposée directement sur Internet.

Architecture : un seul service FastAPI sert HTML via Jinja2.
HTMX gère les mises à jour partielles de la table sans rechargement complet.
Pas de frontend séparé, pas de node_modules, pas de build step.

Note chemin templates : Path(__file__).parent / "templates" résout vers
backend/templates/ indépendamment du CWD au démarrage — compatible Docker
(WORKDIR /app, code dans /app/backend/) et dev local (uvicorn depuis racine
ou depuis backend/).
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from config import (
    EndpointConfig,
    Settings,
    YamlConfig,
    get_settings,
    load_yaml_config,
)
from middleware import SecurityHeadersMiddleware

logger = logging.getLogger("restui")

# Chemin absolu vers templates/ — indépendant du CWD au démarrage.
# En Docker : /app/backend/templates/
# En dev local : <racine_projet>/backend/templates/
_TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


# ---------------------------------------------------------------------------
# Helpers — fonctions pures, testables sans FastAPI
# ---------------------------------------------------------------------------

def _resolve_nested(obj: Any, dot_path: str) -> Any:
    """Résout un chemin dot-notation dans un objet JSON.

    Exemple : _resolve_nested({"a": {"b": 42}}, "a.b") -> 42
    Retourne None si le chemin est inexistant ou si obj n'est pas un dict.
    """
    parts = dot_path.split(".")
    current = obj
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _extract_rows(raw: Any, endpoint: EndpointConfig) -> list[dict[str, Any]]:
    """Extrait la liste de lignes depuis la réponse upstream.

    Si endpoint.parent_field est défini, cherche ce champ dans la réponse.
    Sinon, s'attend à ce que la réponse soit directement une liste.
    Retourne toujours une liste (vide si invalide).
    """
    if endpoint.parent_field:
        rows = raw.get(endpoint.parent_field) if isinstance(raw, dict) else None
    else:
        rows = raw

    if not isinstance(rows, list):
        logger.warning(
            "endpoint=%s — réponse upstream non-liste (type=%s)",
            endpoint.name,
            type(rows).__name__,
        )
        return []
    return rows


def _project_row(row: Any, endpoint: EndpointConfig) -> dict[str, Any]:
    """Projette une ligne brute sur les colonnes déclarées (dot-notation résolue).

    Si aucune colonne n'est déclarée, retourne le dict entier (pass-through).
    """
    if not isinstance(row, dict):
        return {}
    if not endpoint.columns:
        return row
    return {col.key: _resolve_nested(row, col.key) for col in endpoint.columns}


def _apply_filters(
    rows: list[dict[str, Any]],
    filters: dict[str, str],
    endpoint: EndpointConfig,
) -> list[dict[str, Any]]:
    """Filtre les lignes selon les query params actifs.

    Seules les colonnes déclarées filterable: true dans config.yaml sont filtrables.
    Les clés non déclarées sont ignorées silencieusement — pas d'injection de filtre
    arbitraire depuis l'URL.
    Substring match insensible à la casse.
    """
    allowed = set(endpoint.filter_keys)
    active = {
        k: v.lower().strip()
        for k, v in filters.items()
        if k in allowed and v and v.strip()
    }
    if not active:
        return rows

    return [
        row for row in rows
        if all(
            _resolve_nested(row, k) is not None
            and v in str(_resolve_nested(row, k)).lower()
            for k, v in active.items()
        )
    ]


async def _fetch_and_process(
    client: httpx.AsyncClient,
    ep: EndpointConfig,
    query_params: dict[str, str],
) -> tuple[list[dict[str, Any]], str | None]:
    """Appelle l'upstream, projette et filtre.

    Returns:
        (rows, None) si succès.
        ([], message_erreur) si erreur — le message est safe à afficher à l'utilisateur.
    """
    try:
        response = await client.get(ep.url)
        response.raise_for_status()
    except httpx.ConnectTimeout:
        return [], "Timeout de connexion vers l'API."
    except httpx.ReadTimeout:
        return [], "L'API upstream a mis trop longtemps à répondre."
    except httpx.PoolTimeout:
        return [], "Service temporairement indisponible (pool saturé)."
    except httpx.ConnectError as exc:
        logger.error("ConnectError endpoint=%s : %s", ep.name, exc)
        return [], "Impossible de joindre l'API upstream."
    except httpx.HTTPStatusError as exc:
        return [], f"L'API upstream a retourné {exc.response.status_code}."
    except httpx.RequestError as exc:
        logger.error("RequestError endpoint=%s : %s", ep.name, exc)
        return [], "Erreur réseau inattendue."

    try:
        raw = response.json()
    except Exception:
        return [], "La réponse de l'API n'est pas du JSON valide."

    rows_raw = _extract_rows(raw, ep)
    projected = [_project_row(row, ep) for row in rows_raw]
    filtered = _apply_filters(projected, query_params, ep)
    return filtered, None


# ---------------------------------------------------------------------------
# Helper — contexte Jinja2 défensif pour les pages d'erreur
# ---------------------------------------------------------------------------

def _error_context(request: Request, error: str) -> dict[str, Any]:
    """Construit un contexte Jinja2 minimal et défensif pour error.html.

    base.html itère `endpoints` dans la sidebar et accède à `endpoint.name`
    et `endpoint.label` dans le header. Ces clés doivent toujours être présentes
    pour éviter qu'une UndefinedError dans le handler d'erreur ne produise une
    seconde erreur (boucle infinie).

    - endpoints : liste depuis app.state si déjà chargée, sinon liste vide.
    - endpoint : objet stub avec name=None et label="" — la sidebar ne met aucun
      élément en surbrillance et le header affiche une chaîne vide.
    """
    endpoints: list[EndpointConfig] = []
    if hasattr(request.app.state, "yaml_config"):
        endpoints = request.app.state.yaml_config.endpoints

    class _StubEndpoint:
        name: str | None = None
        label: str = ""

    return {
        "error": error,
        "endpoints": endpoints,
        "endpoint": _StubEndpoint(),
    }


# ---------------------------------------------------------------------------
# Lifespan — initialisation et teardown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = get_settings()
    # log_level est normalisé en uppercase par le validator de Settings
    # force=True : remplace la config uvicorn déjà initialisée (sinon basicConfig est no-op)
    logging.basicConfig(level=settings.log_level, force=True)

    try:
        yaml_config: YamlConfig = load_yaml_config(settings.config_yaml_path)
    except (FileNotFoundError, ValueError) as exc:
        logger.critical("Impossible de charger config.yaml : %s", exc)
        raise

    app.state.yaml_config = yaml_config
    logger.info(
        "config.yaml chargé — %d endpoint(s) : %s",
        len(yaml_config.endpoints),
        [ep.name for ep in yaml_config.endpoints],
    )

    # Client HTTP partagé — pool unique, credentials Basic Auth depuis .env.
    # Limits abaissées à 20/5 : adapté Pi5 (pas un serveur dédié haute concurrence).
    app.state.http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=settings.upstream_timeout_connect,
            read=settings.upstream_timeout_read,
            write=10.0,
            pool=5.0,
        ),
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=5,
            keepalive_expiry=30.0,
        ),
        auth=(settings.api_username, settings.api_password),
    )
    logger.info("Client httpx initialisé.")
    yield
    await app.state.http_client.aclose()
    logger.info("Client httpx fermé.")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="RestUI",
        version="1.0.0",
        lifespan=lifespan,
        # /docs exposé uniquement en mode debug — jamais en prod
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    # Security headers en dev local (sans Caddy).
    # En prod, Caddy pose ces headers via le snippet (security_headers) du Caddyfile.
    # Le middleware est idempotent : il ne surcharge pas les headers déjà présents.
    if settings.debug:
        app.add_middleware(SecurityHeadersMiddleware)

    return app


app = create_app()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health", tags=["infra"])
async def health() -> dict[str, str]:
    """Health check — utilisé par Docker (HEALTHCHECK) et Caddy."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Redirect vers le premier endpoint configuré."""
    yaml_config: YamlConfig = request.app.state.yaml_config
    if not yaml_config.endpoints:
        return templates.TemplateResponse(
            request,
            "error.html",
            _error_context(request, "Aucun endpoint configuré dans config.yaml."),
            status_code=503,
        )
    return RedirectResponse(url=f"/{yaml_config.endpoints[0].name}")


# ---------------------------------------------------------------------------
# Routes JSON — déclarées AVANT /{slug}.
# FastAPI résout par spécificité (statique > paramétrique), mais la déclaration
# en premier est la convention explicite — plus lisible, sans ambiguïté.
# ---------------------------------------------------------------------------

@app.get("/api/endpoints", tags=["json-api"])
async def api_endpoints(request: Request) -> list[dict]:
    """Liste des endpoints configurés — disponible pour intégration externe (curl, scripts).

    Retourne uniquement les métadonnées publiques.
    N'expose jamais les URL upstream ni les credentials.
    """
    yaml_config: YamlConfig = request.app.state.yaml_config
    result = []
    for ep in yaml_config.endpoints:
        visible_cols = [c for c in ep.columns if not c.hidden]
        result.append({
            "name": ep.name,
            "label": ep.label,
            # columns : colonnes visibles sans le flag filterable
            # (le frontend reconstruit filterable via la liste filters)
            "columns": [{"key": c.key, "label": c.label} for c in visible_cols],
            # filters : sous-liste des colonnes filtrables
            "filters": [{"key": c.key, "label": c.label} for c in ep.filterable_columns],
        })
    return result


@app.get("/api/data", tags=["json-api"])
async def api_data(request: Request, endpoint: str) -> JSONResponse:
    """Données filtrées d'un endpoint — disponible pour intégration externe (curl, scripts).

    Query params :
      endpoint=<name>        — obligatoire
      <filter_key>=<valeur>  — optionnel, un par colonne filterable

    Retourne : { rows: [...], count: N, endpoint: "<name>" }
    count = nombre de lignes après application des filtres.
    """
    yaml_config: YamlConfig = request.app.state.yaml_config
    client: httpx.AsyncClient = request.app.state.http_client

    ep = yaml_config.get_endpoint(endpoint)
    if ep is None:
        raise HTTPException(status_code=404, detail=f"Endpoint '{endpoint}' introuvable.")

    # Tous les query params sauf 'endpoint' — _apply_filters ne retiendra
    # que les clés déclarées filterable (sécurité : pas de filtre arbitraire).
    filters = {k: v for k, v in request.query_params.items() if k != "endpoint"}
    rows, error = await _fetch_and_process(client, ep, filters)

    if error:
        raise HTTPException(status_code=502, detail=error)

    return JSONResponse({
        "rows": rows,
        "count": len(rows),
        "endpoint": endpoint,
    })


# ---------------------------------------------------------------------------
# Routes HTML — Jinja2 + HTMX
# ---------------------------------------------------------------------------

@app.get("/{slug}", response_class=HTMLResponse)
async def page(request: Request, slug: str):
    """Page complète — layout Jinja2 + table + filtres URL-shareables."""
    yaml_config: YamlConfig = request.app.state.yaml_config
    client: httpx.AsyncClient = request.app.state.http_client

    ep = yaml_config.get_endpoint(slug)
    if ep is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                **_error_context(request, f"Endpoint '{slug}' introuvable."),
                # Surcharge endpoint par None explicite — la sidebar ne surligne rien
            },
            status_code=404,
        )

    rows, error = await _fetch_and_process(client, ep, dict(request.query_params))
    active_filters = {k: request.query_params.get(k, "") for k in ep.filter_keys}

    return templates.TemplateResponse(
        request,
        "table.html",
        {
            "endpoints": yaml_config.endpoints,
            "endpoint": ep,
            "rows": rows,
            "error": error,
            "active_filters": active_filters,
            "total": len(rows) if not error else 0,
        },
    )


@app.get("/{slug}/rows", response_class=HTMLResponse)
async def rows_fragment(request: Request, slug: str):
    """Fragment HTMX — retourne uniquement le <tbody> mis à jour.

    Appelé par HTMX sur changement de filtre. Pas de rechargement de page complet.
    Les filtres actifs sont passés en query params GET — URL shareable par construction.

    Accès direct (sans HX-Request) → redirect vers /{slug}?... pour préserver le layout.
    Le header HX-Push-Url dans la réponse indique à HTMX quelle URL pousser dans
    l'historique (/{slug}?... et non /{slug}/rows?...).
    """
    # Accès direct sans HTMX — redirect vers la page complète avec le même état de filtre
    if not request.headers.get("HX-Request"):
        qs = request.url.query
        redirect_url = f"/{slug}?{qs}" if qs else f"/{slug}"
        return RedirectResponse(url=redirect_url, status_code=302)

    yaml_config: YamlConfig = request.app.state.yaml_config
    client: httpx.AsyncClient = request.app.state.http_client

    ep = yaml_config.get_endpoint(slug)
    if ep is None:
        return HTMLResponse(
            "<tr><td colspan='99' class='px-4 py-8 text-center text-red-600'>"
            "Endpoint introuvable.</td></tr>",
            status_code=404,
        )

    rows, error = await _fetch_and_process(client, ep, dict(request.query_params))

    response = templates.TemplateResponse(
        request,
        "rows.html",
        {"endpoint": ep, "rows": rows, "error": error},
    )
    # Indique à HTMX de pousser /{slug}?filters dans l'historique (pas /{slug}/rows?...)
    # → l'URL copiée depuis le navigateur donne la page complète avec layout
    qs = request.url.query
    response.headers["HX-Push-Url"] = f"/{slug}?{qs}" if qs else f"/{slug}"
    return response


# ---------------------------------------------------------------------------
# Gestionnaire d'erreurs global — retourne HTML, pas JSON
# L'app sert exclusivement du HTML (Jinja2). Un JSONResponse ici serait
# affiché brut dans le navigateur — error.html donne une page cohérente.
#
# Bug corrigé : le contexte inclut systématiquement `endpoints` et `endpoint`
# via _error_context(). Sans ces clés, base.html lève une UndefinedError
# lors du rendu de la sidebar — le handler 500 produirait lui-même une erreur.
# ---------------------------------------------------------------------------

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> HTMLResponse:
    logger.exception("Erreur non gérée pour %s %s", request.method, request.url)
    # En prod (debug=False), le message générique ne divulgue aucun détail interne.
    # _error_context() fournit endpoints + endpoint stub pour base.html.
    return templates.TemplateResponse(
        request,
        "error.html",
        _error_context(request, "Erreur interne du serveur."),
        status_code=500,
    )
