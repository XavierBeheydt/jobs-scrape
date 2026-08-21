"""Enrichissement : applique les greffons installes a chaque offre."""

from __future__ import annotations

import logging
import os

from jobs_scrape import registry

logger = logging.getLogger(__name__)


class EnrichPipeline:
    """Fait tourner les enrichisseurs declares par les modules installes.

    Le coeur ne sait pas ce qu'un enrichisseur fait ; il sait seulement dans
    quel ordre les appeler. Extraire des mots-cles, deviner une seniorite,
    detecter une langue : tout cela vit dans des modules separes, et le jour ou
    aucun n'est installe la chaine continue sans broncher.

    Un enrichisseur qui echoue est signale puis contourne. Une offre non enrichie
    reste une offre exploitable ; une collecte interrompue, non.
    """

    def __init__(self, settings=None):
        self.enrichers = []
        settings = settings or {}
        config = settings.getdict("ENRICHER_CONFIG", {}) if hasattr(settings, "getdict") else {}
        selected = settings.getlist("ENRICHERS", []) if hasattr(settings, "getlist") else []

        metas = sorted(registry.enrichers().values(), key=lambda m: (m.order, m.name))
        for meta in metas:
            if selected and meta.name not in selected:
                continue

            missing = [name for name in meta.requires_env if not os.environ.get(name)]
            if missing:
                logger.warning(
                    "enrichisseur '%s' ignore : variable(s) d'environnement absente(s) : %s",
                    meta.name, ", ".join(missing),
                )
                continue

            options = {**meta.default_config, **config.get(meta.name, {})}
            try:
                self.enrichers.append(meta.factory(**options))
            except Exception:  # noqa: BLE001
                logger.exception("enrichisseur '%s' ignore : initialisation impossible", meta.name)

        if self.enrichers:
            logger.info(
                "enrichisseurs actifs : %s",
                ", ".join(getattr(e, "name", type(e).__name__) for e in self.enrichers),
            )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_item(self, item, spider):
        for enricher in self.enrichers:
            try:
                item = enricher.enrich(item) or item
            except Exception:  # noqa: BLE001
                name = getattr(enricher, "name", type(enricher).__name__)
                spider.crawler.stats.inc_value(f"jobs/enrich_failed/{name}")
                logger.exception("enrichissement '%s' echoue sur %s", name, item.url)
        return item
