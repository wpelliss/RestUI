"""
proxy.py — Fonctions utilitaires testables indépendamment du client httpx.

Le client httpx.AsyncClient est initialisé une seule fois dans le lifespan (main.py)
et stocké dans app.state.http_client. Ce module ne crée jamais de client — il expose
uniquement les fonctions de transformation de données pures.
"""
from __future__ import annotations

from typing import Any

try:
    from config import EndpointConfig
except ImportError:
    from backend.config import EndpointConfig


def resolve_nested(obj: Any, dot_path: str) -> Any:
    """
    Résout un chemin dot-notation dans un objet JSON.

    Exemple :
        resolve_nested({"address": {"city": "Besançon"}}, "address.city")
        → "Besançon"

    Retourne None si le chemin est inexistant ou si obj n'est pas un dict.
    """
    parts = dot_path.split(".")
    current = obj
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def extract_rows(raw: Any, endpoint: EndpointConfig) -> list[dict[str, Any]]:
    """
    Extrait la liste de lignes depuis la réponse JSON upstream.

    - Si endpoint.parent_field est défini, cherche ce champ dans la réponse.
    - Sinon, s'attend à ce que la réponse soit directement une liste.
    - Retourne toujours une liste (vide si la réponse est inattendue).
    """
    if endpoint.parent_field:
        rows = raw.get(endpoint.parent_field) if isinstance(raw, dict) else None
    else:
        rows = raw

    if not isinstance(rows, list):
        return []
    return rows


def project_row(row: Any, endpoint: EndpointConfig) -> dict[str, Any]:
    """
    Projette une ligne brute sur les colonnes déclarées dans config.yaml.
    Résout les chemins dot-notation. Retourne uniquement les clés déclarées.
    Si aucune colonne n'est déclarée, retourne le dict entier.
    """
    if not isinstance(row, dict):
        return {}
    if not endpoint.columns:
        return row
    return {
        col.key: resolve_nested(row, col.key)
        for col in endpoint.columns
    }


def apply_filters(
    rows: list[dict[str, Any]],
    filters: dict[str, str],
    endpoint: EndpointConfig,
) -> list[dict[str, Any]]:
    """
    Filtre les lignes selon les query params reçus.

    - Seuls les filtres déclarés `filterable: true` dans config.yaml sont appliqués.
    - Comparaison insensible à la casse, substring match.
    - Les clés de filtre non déclarées sont ignorées silencieusement.
    """
    allowed_keys = set(endpoint.filter_keys)
    active = {
        k: v.lower().strip()
        for k, v in filters.items()
        if k in allowed_keys and v and v.strip()
    }

    if not active:
        return rows

    result = []
    for row in rows:
        if all(
            resolve_nested(row, key) is not None
            and value in str(resolve_nested(row, key)).lower()
            for key, value in active.items()
        ):
            result.append(row)
    return result
