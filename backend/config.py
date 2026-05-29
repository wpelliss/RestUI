"""
Configuration — pydantic v2 + pydantic-settings.
Lecture depuis .env (Settings) et config.yaml (YamlConfig).

Note architecture : ColumnConfig / EndpointConfig / YamlConfig héritent de
BaseModel — PAS de BaseSettings. BaseSettings lirait l'environnement système
en plus du YAML, créant des collisions silencieuses si une variable d'env
NAME, URL ou KEY existe. BaseModel + model_validate() est le bon pattern.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Modèles de données pour config.yaml — BaseModel
# ---------------------------------------------------------------------------

class ColumnConfig(BaseModel):
    """Description d'une colonne affichée dans la table."""

    model_config = {"extra": "ignore"}

    key: str = Field(
        description="Chemin dot-notation vers la valeur JSON (ex: 'address.city')."
    )
    label: str = Field(
        description="Libellé affiché dans l'en-tête de colonne."
    )
    filterable: bool = Field(
        default=False,
        description="Si True, cette colonne apparaît comme filtre URL.",
    )
    hidden: bool = Field(
        default=False,
        description="Si True, colonne présente dans les données mais masquée par défaut.",
    )


class EndpointConfig(BaseModel):
    """Déclaration complète d'un endpoint proxifié."""

    model_config = {"extra": "ignore"}

    name: str = Field(
        description="Identifiant unique de l'endpoint (slug URL : /{name})."
    )
    label: str = Field(
        description="Libellé lisible affiché dans le sidebar."
    )
    url: str = Field(
        description="URL complète de l'API upstream."
    )
    parent_field: str | None = Field(
        default=None,
        description=(
            "Clé JSON du tableau de résultats quand la réponse est un objet "
            "(ex: 'users' pour {'users': [...]}). None si la réponse est déjà un tableau."
        ),
    )
    columns: list[ColumnConfig] = Field(
        default_factory=list,
        description="Liste ordonnée des colonnes à exposer.",
    )

    @property
    def filterable_columns(self) -> list[ColumnConfig]:
        return [c for c in self.columns if c.filterable]

    @property
    def filter_keys(self) -> list[str]:
        return [c.key for c in self.filterable_columns]


class YamlConfig(BaseModel):
    """Racine du config.yaml."""

    model_config = {"extra": "ignore"}

    endpoints: list[EndpointConfig] = Field(default_factory=list)

    def get_endpoint(self, name: str) -> EndpointConfig | None:
        for ep in self.endpoints:
            if ep.name == name:
                return ep
        return None


# ---------------------------------------------------------------------------
# Settings depuis .env
# ---------------------------------------------------------------------------

class Settings(BaseSettings):
    """
    Variables d'environnement lues depuis .env.
    Aucune valeur sensible ne doit apparaître en dur dans ce fichier.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Credentials upstream — obligatoires, pas de fallback
    api_username: str = Field(
        description="Login HTTP Basic Auth pour l'API upstream."
    )
    api_password: str = Field(
        description="Mot de passe HTTP Basic Auth pour l'API upstream."
    )

    # Timeouts httpx
    upstream_timeout_connect: float = Field(
        default=5.0,
        description="Timeout de connexion TCP vers l'upstream (secondes).",
    )
    upstream_timeout_read: float = Field(
        default=30.0,
        description="Timeout de lecture de la réponse upstream (secondes).",
    )

    # Chemin vers config.yaml (relatif au CWD au démarrage)
    config_yaml_path: str = Field(
        default="config.yaml",
        description="Chemin vers le fichier de configuration YAML des endpoints.",
    )

    # Mode debug — active /docs uniquement. Ne bypass jamais l'auth Caddy.
    debug: bool = Field(default=False)

    # Niveau de log — info en prod, debug en dev
    log_level: str = Field(
        default="INFO",
        description="Niveau de log Python (DEBUG, INFO, WARNING, ERROR).",
    )

    @field_validator("api_username", "api_password", mode="before")
    @classmethod
    def must_not_be_empty(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.strip():
            raise ValueError("La valeur ne peut pas être vide.")
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.upper()
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Parse .env une seule fois, résultat mis en cache."""
    return Settings()


# ---------------------------------------------------------------------------
# Chargement YAML
# ---------------------------------------------------------------------------

def load_yaml_config(path: str) -> YamlConfig:
    """
    Charge et valide config.yaml.
    Lève FileNotFoundError ou ValueError si le fichier est absent ou malformé.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(
            f"config.yaml introuvable : {config_path.absolute()}"
        )
    with config_path.open("r", encoding="utf-8") as fh:
        raw: Any = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        raise ValueError("config.yaml doit être un mapping YAML valide.")

    return YamlConfig.model_validate(raw)
