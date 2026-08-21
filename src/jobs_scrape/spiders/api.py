"""Socle des collecteurs qui interrogent une interface JSON.

Scrapy est souvent presente comme un outil d'analyse de HTML ; c'est en realite
un moteur de requetes HTTP asynchrone, et rien ne l'oblige a recevoir du balisage.
Appeler une API depuis Scrapy plutot qu'avec une boucle ``requests`` fait gagner,
sans une ligne de code supplementaire : la limitation de debit adaptative, les
reessais avec backoff, le cache disque, les statistiques, et surtout la meme
chaine de pipelines que les collecteurs HTML -- donc le meme schema en sortie.

Deux des sources du projet fonctionnent ainsi (Job-Room et APEC), et ce sont les
plus fiables du lot.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from scrapy.http import JsonRequest, Request, Response

from jobs_scrape.items import JobItem
from jobs_scrape.spiders.base import BaseJobSpider


class ApiJobSpider(BaseJobSpider):
    """Collecteur d'API JSON paginee.

    Un module concret fixe ``endpoint``, puis implemente ``extract_rows`` et
    ``parse_row``. La pagination, l'arret et la construction des requetes sont
    deja pris en charge ici.
    """

    endpoint: str = ""
    method: str = "POST"

    page_param: str = "page"
    size_param: str = "size"
    page_size: int = 100
    start_page: int = 0

    max_pages: int | None = None
    """Garde-fou. ``None`` signifie : jusqu'a ce que l'API n'ait plus rien."""

    # -- a redefinir dans les modules -------------------------------------

    def payload(self, page: int) -> dict[str, Any] | None:
        """Corps JSON de la requete. ``None`` pour un appel sans corps (GET)."""
        return None

    def query_params(self, page: int) -> dict[str, Any]:
        """Parametres d'URL. Par defaut, la pagination."""
        return {self.page_param: page, self.size_param: self.page_size}

    def headers(self) -> dict[str, str]:
        return {"Accept": "application/json"}

    def extract_rows(self, response: Response) -> list[Any]:
        """Enregistrements bruts contenus dans la reponse."""
        data = response.json()
        return data if isinstance(data, list) else []

    def parse_row(self, row: Any, response: Response) -> JobItem | None:
        """Traduit un enregistrement brut en ``JobItem``. ``None`` pour l'ignorer."""
        raise NotImplementedError

    def has_next_page(self, response: Response, rows: list[Any], page: int) -> bool:
        """Decide s'il faut demander la page suivante.

        Regle par defaut : une page pleine laisse supposer qu'il y a une suite.
        Les API qui exposent un total ou un lien ``next`` peuvent faire mieux, et
        les modules concernes redefinissent cette methode.
        """
        if self.max_pages is not None and (page - self.start_page + 1) >= self.max_pages:
            return False
        return len(rows) >= self.page_size

    # -- mecanique ---------------------------------------------------------

    def build_request(self, page: int) -> Request:
        params = self.query_params(page)
        url = self.endpoint
        if params:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(params, doseq=True)}"

        body = self.payload(page)
        meta = {"page": page}

        if body is not None:
            # JsonRequest serialise le corps et pose Content-Type tout seul.
            return JsonRequest(
                url=url, data=body, method=self.method, headers=self.headers(),
                callback=self.parse, meta=meta, dont_filter=True,
            )
        return Request(
            url=url, method="GET", headers=self.headers(),
            callback=self.parse, meta=meta, dont_filter=True,
        )

    async def start(self):
        yield self.build_request(self.start_page)

    def parse(self, response: Response, **kwargs):
        page = response.meta.get("page", self.start_page)

        try:
            rows = self.extract_rows(response)
        except ValueError:
            self.logger.error(
                "reponse non-JSON sur %s (HTTP %s) ; page ignoree",
                response.url, response.status,
            )
            return

        for row in rows:
            if self.limit_reached():
                return
            try:
                item = self.parse_row(row, response)
            except Exception:  # noqa: BLE001 - une annonce malformee n'arrete pas la collecte
                self.logger.exception("enregistrement illisible, ignore")
                continue
            if item is not None:
                yield item

        if not self.limit_reached() and self.has_next_page(response, rows, page):
            yield self.build_request(page + 1)
