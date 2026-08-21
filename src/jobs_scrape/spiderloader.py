"""Chargeur de spiders branche sur le registre de modules.

Scrapy decouvre normalement ses spiders en parcourant les paquets listes dans
``SPIDER_MODULES``. Ce mecanisme est statique : il suppose que les spiders vivent
dans l'arborescence du projet. Ici ils vivent dans des distributions separees,
installees a la demande, et resteraient donc invisibles.

Scrapy prevoit ce cas : ``SPIDER_LOADER_CLASS`` permet de substituer sa propre
implementation. Celle-ci se contente de rediriger vers le registre d'entry
points, ce qui rend les modules externes indiscernables de spiders natifs pour
le reste du framework -- ``scrapy crawl``, les stats et les extensions
fonctionnent sans rien savoir du systeme de modules.
"""

from __future__ import annotations

import logging

from scrapy.interfaces import ISpiderLoader
from zope.interface import implementer

from jobs_scrape import registry

logger = logging.getLogger(__name__)


@implementer(ISpiderLoader)
class RegistrySpiderLoader:
    """Expose a Scrapy les spiders fournis par les modules installes."""

    def __init__(self, settings=None):
        self.settings = settings
        self._spiders: dict[str, type] = {}
        self._load_all()

    # -- construction attendue par Scrapy --------------------------------
    # Scrapy 2.13 a introduit ``from_crawler`` et deprecie ``from_settings``.
    # Les deux sont fournis pour rester compatible avec les deux generations.

    @classmethod
    def from_settings(cls, settings):
        return cls(settings)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    # -- interface ISpiderLoader -----------------------------------------

    def _load_all(self) -> None:
        self._spiders = {
            name: meta.spider for name, meta in registry.sources().items()
        }
        for name, spider in self._spiders.items():
            # Scrapy identifie un spider par son attribut ``name``. On aligne
            # celui-ci sur le nom declare par le module pour que les deux
            # coincident toujours, meme si l'auteur du module les a divergees.
            if getattr(spider, "name", None) != name:
                spider.name = name

    def load(self, spider_name: str):
        try:
            return self._spiders[spider_name]
        except KeyError:
            known = ", ".join(sorted(self._spiders)) or "aucun"
            raise KeyError(
                f"spider '{spider_name}' introuvable. Disponibles : {known}"
            ) from None

    def list(self) -> list[str]:
        return sorted(self._spiders)

    def find_by_request(self, request) -> list[str]:
        """Spiders declarant gerer le domaine de cette requete."""
        from scrapy.utils.url import url_is_from_any_domain

        return [
            name
            for name, spider in self._spiders.items()
            if url_is_from_any_domain(request.url, getattr(spider, "allowed_domains", []) or [])
        ]
