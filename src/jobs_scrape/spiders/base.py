"""Tronc commun a tous les collecteurs."""

from __future__ import annotations

import scrapy

from jobs_scrape.items import JobItem
from jobs_scrape.loaders import utc_now_iso


class BaseJobSpider(scrapy.Spider):
    """Socle partage : identite de la source, limite d'extraction, horodatage.

    Un collecteur n'herite jamais directement de cette classe : il passe par
    ``ApiJobSpider``, ``HtmlJobSpider`` ou ``SitemapJobSpider``, qui ajoutent la
    mecanique propre a leur mode d'acces.
    """

    source_name: str = ""
    """Nom de la source. Vide, on retombe sur ``name``."""

    def __init__(self, limit: str | int | None = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # La limite arrive de la ligne de commande (``-a limit=50``), donc en
        # chaine. On l'accepte aussi en entier pour les appels programmatiques.
        self.limit: int | None = int(limit) if limit not in (None, "", "0") else None
        self.emitted: int = 0

    @property
    def source(self) -> str:
        return self.source_name or self.name

    def limit_reached(self) -> bool:
        """Vrai quand le quota demande est atteint.

        Les collecteurs testent cette methode avant de produire une offre, et
        avant de demander la page suivante. C'est ce qui rend
        ``--limit`` reellement econome : on arrete de solliciter le serveur des
        que le compte y est, au lieu de tout telecharger puis de tronquer.
        """
        return self.limit is not None and self.emitted >= self.limit

    def new_item(self, **values) -> JobItem:
        """Fabrique une offre en remplissant l'identite de la source."""
        values.setdefault("source", self.source)
        values.setdefault("scraped_at", utc_now_iso())
        self.emitted += 1
        return JobItem(**values)
