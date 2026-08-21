"""Deduplication a l'interieur d'une meme collecte."""

from __future__ import annotations

from scrapy.exceptions import DropItem


class DedupePipeline:
    """Ecarte les offres deja vues pendant ce passage.

    Les doublons intra-collecte sont frequents et normaux : une meme annonce
    apparait sous plusieurs mots-cles de recherche, ou dans plusieurs categories
    du site. Les ecarter ici evite un travail d'enrichissement inutile en aval.

    Les doublons **entre** collectes, eux, ne sont pas traites ici : le stockage
    s'en charge par ``UPSERT`` sur l'empreinte, ce qui met a jour l'annonce
    existante et rafraichit sa date de derniere vue sans en creer une seconde.
    """

    def __init__(self):
        self.seen: set[str] = set()

    def process_item(self, item, spider):
        fingerprint = item.fingerprint
        if not fingerprint:
            # Sans empreinte on laisse passer : la normalisation aurait du en
            # poser une, et bloquer ici masquerait le vrai probleme.
            return item
        if fingerprint in self.seen:
            spider.crawler.stats.inc_value("jobs/dropped/duplicate")
            raise DropItem(f"doublon dans cette collecte : {item.url}")
        self.seen.add(fingerprint)
        return item
