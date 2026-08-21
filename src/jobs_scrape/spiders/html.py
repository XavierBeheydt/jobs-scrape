"""Socle des collecteurs qui parcourent une liste puis des pages de detail."""

from __future__ import annotations

import re
from typing import Any

import scrapy
from scrapy.http import Response

from jobs_scrape import jsonld
from jobs_scrape.items import JobItem
from jobs_scrape.spiders.base import BaseJobSpider


class HtmlJobSpider(BaseJobSpider):
    """Collecteur « page de resultats puis fiche d'offre ».

    Le partage du travail est le suivant : cette classe gere la pagination, le
    suivi des liens et l'application du quota ; le module concret decrit ou sont
    les liens et comment lire une fiche.

    Deux facons de lire une fiche, combinables :

    * si la page publie un ``JobPosting`` JSON-LD, il est exploite tel quel et le
      module n'a rien a ecrire ;
    * ``extra_fields()`` permet d'ajouter ou de corriger des champs par
      selecteurs CSS. Ce qu'elle renvoie prime sur le JSON-LD, parce qu'un
      module sait mieux que la regle generale ce que son site raconte.
    """

    listing_urls: list[str] = []
    detail_link_css: str = ""
    detail_link_xpath: str = ""
    detail_url_re: str = ""
    """Filtre applique aux liens collectes, pour ecarter les faux positifs."""

    next_page_css: str = ""
    max_pages: int | None = None
    use_jsonld: bool = True

    # -- points d'extension -----------------------------------------------

    def build_listing_urls(self) -> list[str]:
        """URLs de depart. A redefinir pour construire une recherche depuis les arguments."""
        return list(self.listing_urls)

    def extra_fields(self, response: Response) -> dict[str, Any]:
        """Champs extraits par selecteurs, appliques par-dessus le JSON-LD."""
        return {}

    def accept(self, fields: dict[str, Any], response: Response) -> bool:
        """Dernier filtre avant emission. Permet d'ecarter les annonces expirees."""
        return bool(fields.get("title"))

    # -- mecanique ---------------------------------------------------------

    async def start(self):
        for url in self.build_listing_urls():
            yield scrapy.Request(url, callback=self.parse_listing, meta={"page": 1})

    def parse_listing(self, response: Response, **kwargs):
        page = response.meta.get("page", 1)

        links: list[str] = []
        if self.detail_link_css:
            links += response.css(self.detail_link_css).getall()
        if self.detail_link_xpath:
            links += response.xpath(self.detail_link_xpath).getall()
        if not links:
            links = response.css("a::attr(href)").getall()

        if self.detail_url_re:
            pattern = re.compile(self.detail_url_re)
            links = [href for href in links if href and pattern.search(href)]

        seen: set[str] = set()
        for href in links:
            if self.limit_reached():
                return
            url = response.urljoin(href)
            if url in seen:
                continue
            seen.add(url)
            yield scrapy.Request(url, callback=self.parse_detail)

        if self.limit_reached():
            return
        if self.max_pages is not None and page >= self.max_pages:
            return
        if self.next_page_css:
            next_href = response.css(self.next_page_css).get()
            if next_href:
                yield scrapy.Request(
                    response.urljoin(next_href),
                    callback=self.parse_listing,
                    meta={"page": page + 1},
                )

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
