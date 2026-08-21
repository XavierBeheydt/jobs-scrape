"""Socle des collecteurs guides par un sitemap XML.

Certains sites interdisent leurs pages de recherche dans ``robots.txt`` tout en
publiant un sitemap complet des annonces. ApproachPeople est dans ce cas : ses
chemins ``/job-search*`` et ``/*?`` sont fermes, mais ``job-sitemap.xml``
enumere les 1 129 offres. Passer par le sitemap est alors la seule voie
conforme -- et accessoirement la plus fiable, puisqu'elle ne depend d'aucune
pagination.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from scrapy.http import Response
from scrapy.spiders import SitemapSpider

from jobs_scrape import jsonld
from jobs_scrape.items import JobItem
from jobs_scrape.spiders.base import BaseJobSpider


class SitemapJobSpider(BaseJobSpider, SitemapSpider):
    """Collecteur pilote par sitemap.

    L'ordre d'heritage compte : ``BaseJobSpider`` apporte le quota et la
    fabrication d'offres, ``SitemapSpider`` apporte le telechargement et le
    deroulage des sitemaps, y compris les index et les fichiers compresses.
    """

    sitemap_urls: list[str] = []
    sitemap_rules = [("", "parse_detail")]
    use_jsonld: bool = True

    def sitemap_filter(self, entries) -> Iterator[dict]:
        """Ecarte les entrees au-dela du quota demande.

        Sans ce filtre, ``--limit 20`` mettrait quand meme un millier de requetes
        en file avant que le quota ne s'applique cote extraction. On tronque donc
        des la lecture du sitemap : le site n'est sollicite que pour ce qui sera
        reellement utilise.
        """
        emitted = 0
        for entry in entries:
            if self.limit is not None and emitted >= self.limit:
                return
            emitted += 1
            yield entry

    def extra_fields(self, response: Response) -> dict[str, Any]:
        """Champs extraits par selecteurs, appliques par-dessus le JSON-LD."""
        return {}

    def accept(self, fields: dict[str, Any], response: Response) -> bool:
        return bool(fields.get("title"))

    def parse_detail(self, response: Response, **kwargs) -> JobItem | None:
        if self.limit_reached():
            return None

        fields: dict[str, Any] = {}
        if self.use_jsonld:
            posting = jsonld.find_jobposting(response)
            if posting:
                fields.update(jsonld.to_fields(posting, url=response.url))

        fields.update(self.extra_fields(response))
        fields.setdefault("url", response.url)

        if not self.accept(fields, response):
            self.logger.debug("offre ecartee : %s", response.url)
            return None
        return self.new_item(**fields)
