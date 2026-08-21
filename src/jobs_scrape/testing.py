"""Harnais de test offert aux modules.

Un module de collecte doit pouvoir etre teste **sans reseau**. Ce n'est pas un
confort : des tests qui appellent le vrai site sont lents, deviennent rouges le
jour ou la source change une virgule, et sollicitent un serveur tiers a chaque
execution de la CI -- ce qui serait contradictoire avec la sobriete affichee par
ailleurs.

La marche a suivre pour un module : figer une reponse reelle dans
``tests/fixtures/``, la rejouer ici, verifier les champs produits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scrapy.http import HtmlResponse, Request, TextResponse

from jobs_scrape.items import REQUIRED_FIELDS, JobItem


def html_response(url: str, body: str | bytes, **meta: Any) -> HtmlResponse:
    """Reponse HTML rejouee depuis une fixture."""
    if isinstance(body, str):
        body = body.encode("utf-8")
    request = Request(url=url, meta=meta or None)
    return HtmlResponse(url=url, body=body, encoding="utf-8", request=request)


def json_response(url: str, payload: Any, **meta: Any) -> TextResponse:
    """Reponse JSON rejouee, prete pour ``response.json()``."""
    body = payload if isinstance(payload, (str, bytes)) else json.dumps(payload)
    if isinstance(body, str):
        body = body.encode("utf-8")
    request = Request(url=url, meta=meta or None)
    return TextResponse(
        url=url, body=body, encoding="utf-8", request=request,
        headers={"Content-Type": "application/json"},
    )


def load_fixture(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def collect(result) -> list[JobItem]:
    """Ne garde que les offres d'un resultat de callback.

    Un callback melange couramment offres et requetes de suivi ; les tests
    portent sur les premieres.
    """
    if result is None:
        return []
    if isinstance(result, JobItem):
        return [result]
    return [entry for entry in result if isinstance(entry, JobItem)]


def assert_usable(item: JobItem) -> None:
    """Verifie qu'une offre passerait la validation du pipeline."""
    missing = [name for name in REQUIRED_FIELDS if not getattr(item, name, None)]
    assert not missing, f"champs obligatoires manquants : {', '.join(missing)}"
    assert str(item.url).startswith(("http://", "https://")), f"URL invalide : {item.url}"


class StubSpider:
    """Spider minimal pour tester un pipeline isolement."""

    def __init__(self, name: str = "test"):
        self.name = name
        self.crawler = _StubCrawler()

    @property
    def stats(self) -> dict[str, int]:
        return self.crawler.stats.values


class _StubStats:
    def __init__(self):
        self.values: dict[str, int] = {}

    def inc_value(self, key: str, count: int = 1, **kwargs) -> None:
        self.values[key] = self.values.get(key, 0) + count

    def get_value(self, key: str, default=None):
        return self.values.get(key, default)


class _StubCrawler:
    def __init__(self):
        self.stats = _StubStats()
