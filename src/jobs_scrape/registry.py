"""Decouverte des modules installes, via les entry points Python.

Le coeur ne connait aucun module a l'avance et n'en importe aucun en dur : il
lit le groupe d'entry points ``jobs_scrape.sources`` (collecteurs) et
``jobs_scrape.enrichers`` (enrichisseurs) de l'environnement courant.

Consequence directe : ``jobs-scrape`` s'installe et tourne seul, sans le moindre
collecteur. Installer un module suffit a le rendre visible, le desinstaller
suffit a le retirer -- aucun fichier du coeur n'est a modifier.

Un module defaillant est signale puis ignore. Une dependance manquante dans un
collecteur ne doit pas priver l'utilisateur des dix autres.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from jobs_scrape.source import EnricherMeta, SourceMeta

logger = logging.getLogger(__name__)

SOURCE_GROUP = "jobs_scrape.sources"
ENRICHER_GROUP = "jobs_scrape.enrichers"

_cache: dict[str, dict] = {}


def _discover(group: str, expected: type) -> dict:
    found: dict[str, object] = {}
    for entry in entry_points(group=group):
        try:
            meta = entry.load()
        except Exception as exc:  # noqa: BLE001 - un module casse ne doit pas tout bloquer
            logger.warning("module '%s' ignore : chargement impossible (%s)", entry.name, exc)
            continue
        if not isinstance(meta, expected):
            logger.warning(
                "module '%s' ignore : %s attendu, %s recu",
                entry.name, expected.__name__, type(meta).__name__,
            )
            continue
        if meta.name != entry.name:
            logger.debug(
                "module '%s' declare le nom interne '%s' ; c'est ce dernier qui fait foi",
                entry.name, meta.name,
            )
        found[meta.name] = meta
    return dict(sorted(found.items()))


def sources(refresh: bool = False) -> dict[str, SourceMeta]:
    """Collecteurs installes, indexes par nom."""
    if refresh or SOURCE_GROUP not in _cache:
        _cache[SOURCE_GROUP] = _discover(SOURCE_GROUP, SourceMeta)
    return _cache[SOURCE_GROUP]


def enrichers(refresh: bool = False) -> dict[str, EnricherMeta]:
    """Enrichisseurs installes, indexes par nom."""
    if refresh or ENRICHER_GROUP not in _cache:
        _cache[ENRICHER_GROUP] = _discover(ENRICHER_GROUP, EnricherMeta)
    return _cache[ENRICHER_GROUP]


def get_source(name: str) -> SourceMeta:
    """Un collecteur par son nom, ou une erreur qui dit quoi faire."""
    available = sources()
    if name not in available:
        known = ", ".join(available) or "aucun"
        raise KeyError(
            f"collecteur '{name}' introuvable. Installes : {known}. "
            f"Pour en ajouter un : jobs-scrape modules sync"
        )
    return available[name]


def get_enricher(name: str) -> EnricherMeta:
    """Un enrichisseur par son nom."""
    available = enrichers()
    if name not in available:
        known = ", ".join(available) or "aucun"
        raise KeyError(f"enrichisseur '{name}' introuvable. Installes : {known}")
    return available[name]


def clear_cache() -> None:
    """Oublie la decouverte precedente. Utile apres une installation de module."""
    _cache.clear()
