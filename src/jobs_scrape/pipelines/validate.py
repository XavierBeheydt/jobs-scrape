"""Validation : ecarte les offres inexploitables."""

from __future__ import annotations

from scrapy.exceptions import DropItem

from jobs_scrape.items import REQUIRED_FIELDS


class ValidatePipeline:
    """Verifie le minimum vital : une source, une URL, un intitule.

    Le seuil est volontairement bas. Une annonce sans salaire ni localisation
    reste utile ; une annonce sans intitule ou sans lien ne l'est pas -- on ne
    peut ni l'afficher, ni y postuler. Tout le reste est facultatif, parce que
    les sources sont tres inegales et qu'exiger davantage reviendrait a jeter
    des offres valables.
    """

    def process_item(self, item, spider):
        missing = [
            name for name in REQUIRED_FIELDS if not getattr(item, name, None)
        ]
        if missing:
            spider.crawler.stats.inc_value("jobs/dropped/incomplete")
            raise DropItem(
                f"offre incomplete, champs manquants : {', '.join(missing)} "
                f"({getattr(item, 'url', None) or 'sans URL'})"
            )

        url = str(item.url)
        if not url.startswith(("http://", "https://")):
            spider.crawler.stats.inc_value("jobs/dropped/bad_url")
            raise DropItem(f"URL inutilisable : {url!r}")

        spider.crawler.stats.inc_value("jobs/valid")
        return item
