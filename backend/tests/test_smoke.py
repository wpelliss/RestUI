"""
Smoke tests — vérifient les invariants critiques sans infra réelle.

Pas de test d'intégration (pas d'API upstream en CI).
Objectif : attraper les régressions sur le proxy et le filtrage.

Lancer depuis la racine du projet :
    pytest backend/tests/ -v
ou via :
    make test
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Credentials factices requis par pydantic-settings au moment de l'import de main.py
# (le validator refuse les valeurs vides — des valeurs non-vides suffisent pour les tests unitaires)
os.environ.setdefault("API_USERNAME", "test_user")
os.environ.setdefault("API_PASSWORD", "test_password")

# Ajoute backend/ au path pour résoudre les imports absolus de main.py
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import _apply_filters, _extract_rows, _project_row, _resolve_nested  # noqa: E402


# ---------------------------------------------------------------------------
# _resolve_nested
# ---------------------------------------------------------------------------

def test_resolve_nested_flat():
    assert _resolve_nested({"id": 42}, "id") == 42


def test_resolve_nested_dot():
    obj = {"address": {"city": "Besançon"}}
    assert _resolve_nested(obj, "address.city") == "Besançon"


def test_resolve_nested_missing_key():
    assert _resolve_nested({"a": 1}, "b") is None


def test_resolve_nested_non_dict_intermediate():
    obj = {"a": "not_a_dict"}
    assert _resolve_nested(obj, "a.b") is None


def test_resolve_nested_empty_path():
    assert _resolve_nested({"": "root"}, "") == "root"


# ---------------------------------------------------------------------------
# _extract_rows
# ---------------------------------------------------------------------------

class FakeEndpoint:
    """Stub minimal d'EndpointConfig pour les tests unitaires."""

    def __init__(self, parent_field=None, columns=None, filter_keys=None):
        self.parent_field = parent_field
        self.columns = columns or []
        self.filter_keys = filter_keys or []
        self.name = "test"


def test_extract_rows_direct_list():
    raw = [{"id": 1}, {"id": 2}]
    ep = FakeEndpoint()
    assert _extract_rows(raw, ep) == raw


def test_extract_rows_parent_field():
    raw = {"users": [{"id": 1}]}
    ep = FakeEndpoint(parent_field="users")
    assert _extract_rows(raw, ep) == [{"id": 1}]


def test_extract_rows_missing_parent_field():
    raw = {"other": []}
    ep = FakeEndpoint(parent_field="users")
    assert _extract_rows(raw, ep) == []


def test_extract_rows_non_list():
    ep = FakeEndpoint()
    assert _extract_rows({"key": "val"}, ep) == []


# ---------------------------------------------------------------------------
# _apply_filters
# ---------------------------------------------------------------------------

def test_apply_filters_no_active():
    rows = [{"status": "active"}, {"status": "inactive"}]
    ep = FakeEndpoint(filter_keys=["status"])
    assert _apply_filters(rows, {}, ep) == rows


def test_apply_filters_substring_match():
    # "act" est substring de "inactive" aussi — utiliser "pending" qui ne contient pas "act"
    rows = [{"status": "active"}, {"status": "pending"}]
    ep = FakeEndpoint(filter_keys=["status"])
    result = _apply_filters(rows, {"status": "act"}, ep)
    assert len(result) == 1
    assert result[0]["status"] == "active"


def test_apply_filters_case_insensitive():
    rows = [{"city": "Besançon"}, {"city": "Paris"}]
    ep = FakeEndpoint(filter_keys=["city"])
    result = _apply_filters(rows, {"city": "besançon"}, ep)
    assert len(result) == 1


def test_apply_filters_undeclared_key_ignored():
    rows = [{"status": "active"}]
    ep = FakeEndpoint(filter_keys=["status"])
    # "secret" n'est pas dans filter_keys → ignoré même si présent dans query params
    result = _apply_filters(rows, {"secret": "anything"}, ep)
    assert result == rows


def test_apply_filters_empty_value_ignored():
    rows = [{"status": "active"}, {"status": "inactive"}]
    ep = FakeEndpoint(filter_keys=["status"])
    result = _apply_filters(rows, {"status": "  "}, ep)
    assert result == rows


def test_apply_filters_multiple_keys():
    # "inactive" contient "active" en substring — utiliser "pending" pour lever l'ambiguïté
    rows = [
        {"status": "active", "city": "Paris"},
        {"status": "active", "city": "Lyon"},
        {"status": "pending", "city": "Paris"},
    ]
    ep = FakeEndpoint(filter_keys=["status", "city"])
    result = _apply_filters(rows, {"status": "active", "city": "paris"}, ep)
    assert len(result) == 1
    assert result[0]["city"] == "Paris"
