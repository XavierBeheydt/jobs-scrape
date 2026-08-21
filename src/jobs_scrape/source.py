"""Contrat entre le coeur et les modules externes.

Un module ne fournit pas seulement du code : il fournit aussi ce qu'il faut
savoir pour l'utiliser correctement -- son mode d'acces, les domaines qu'il
touche, les cles dont il a besoin, et les reserves juridiques ou techniques qui
le concernent. C'est le role de :class:`SourceMeta`.

Cette information est declarative et lisible sans executer le spider, ce qui
permet a ``jobs-scrape list`` de renseigner l'utilisateur avant toute requete.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

AccessMode = Literal["api", "html", "sitemap", "mixed"]
"""Comment le module atteint ses donnees.

``api``      appel d'une interface JSON documentee ou observable
``html``     analyse de pages rendues
``sitemap``  parcours guide par un sitemap XML
``mixed``    combinaison des precedents
"""


@dataclass(frozen=True)
class SourceMeta:
    """Carte d'identite d'un module de collecte."""

    name: str
    """Identifiant court, sans espace. Sert de nom de spider et de cle CLI."""

    spider: type
    """Classe du spider, sous-classe d'une des bases de ``jobs_scrape.spiders``."""

    access: AccessMode
    country: str
    """Zone couverte : ``CH``, ``FR``, ou ``CH/FR``."""

    domains: tuple[str, ...] = ()
    description: str = ""

    enabled_by_default: bool = True
    """Faux pour les modules qu'on livre sans pouvoir garantir qu'ils aboutissent."""

    notes: str = ""
    """Reserves connues : blocage technique, restriction de CGU, limite de volume."""

    requires_env: tuple[str, ...] = ()
    """Variables d'environnement sans lesquelles le module ne peut pas tourner."""

    def missing_env(self) -> tuple[str, ...]:
        """Variables d'environnement declarees mais absentes."""
        import os

        return tuple(name for name in self.requires_env if not os.environ.get(name))


@runtime_checkable
class Enricher(Protocol):
    """Transformation appliquee a chaque offre apres deduplication."""

    name: str

    def enrich(self, item: Any) -> Any:
        """Renvoie l'offre enrichie. Doit etre tolerante : en cas de doute, ne rien faire."""
        ...


@dataclass(frozen=True)
class EnricherMeta:
    """Carte d'identite d'un module d'enrichissement."""

    name: str

    factory: Callable[..., Enricher]
    """Appele avec la configuration du module ; renvoie une instance d'``Enricher``."""

    description: str = ""
    order: int = 500
    """Rang d'execution parmi les enrichisseurs. Croissant."""

    default_config: dict[str, Any] = field(default_factory=dict)
    requires_env: tuple[str, ...] = ()
