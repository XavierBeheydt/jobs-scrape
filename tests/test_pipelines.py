"""Chaine de traitement : normalisation, validation, deduplication."""

import pytest
from conftest import make_job
from scrapy.exceptions import DropItem

from jobs_scrape.items import JobItem
from jobs_scrape.pipelines.dedupe import DedupePipeline
from jobs_scrape.pipelines.enrich import EnrichPipeline
from jobs_scrape.pipelines.normalize import NormalizePipeline
from jobs_scrape.pipelines.validate import ValidatePipeline
from jobs_scrape.testing import StubSpider


@pytest.fixture
def spider():
    return StubSpider()


def test_normalise_dates_pays_et_empreinte(spider):
    item = JobItem(source="x", url="https://x/1", title="  Chef  de projet ",
                   country="Suisse", posted_at="21/08/2026")
    out = NormalizePipeline().process_item(item, spider)
    assert out.title == "Chef de projet"
    assert out.country == "CH"
    assert out.posted_at == "2026-08-21"
    assert out.fingerprint


def test_normalise_accepte_un_dictionnaire(spider):
    """Un module peut renvoyer un dict ; les cles inconnues sont ignorees."""
    out = NormalizePipeline().process_item(
        {"source": "x", "url": "https://x/1", "title": "T", "cle_inventee": 1}, spider
    )
    assert isinstance(out, JobItem) and out.title == "T"


def test_normalise_borne_et_reordonne_le_taux(spider):
    out = NormalizePipeline().process_item(
        JobItem(source="x", url="https://x/1", title="T",
                workload_min=150, workload_max=-10), spider)
    assert (out.workload_min, out.workload_max) == (0, 100)


def test_normalise_dedoublonne_les_listes(spider):
    out = NormalizePipeline().process_item(
        JobItem(source="x", url="https://x/1", title="T",
                skills=["python", "python", " Go ", None]), spider)
    assert out.skills == ["python", "Go"]


@pytest.mark.parametrize("missing", ["source", "url", "title"])
def test_validation_exige_le_minimum_vital(spider, missing):
    item = make_job(**{missing: None})
    with pytest.raises(DropItem):
        ValidatePipeline().process_item(item, spider)


def test_validation_refuse_une_url_non_http(spider):
    with pytest.raises(DropItem):
        ValidatePipeline().process_item(make_job(url="ftp://x/1"), spider)


def test_validation_accepte_une_offre_minimale(spider):
    """Sans salaire ni lieu, une offre reste utile : le seuil doit rester bas."""
    item = JobItem(source="x", url="https://x/1", title="T")
    assert ValidatePipeline().process_item(item, spider) is item
    assert spider.stats["jobs/valid"] == 1


def test_dedup_intra_collecte(spider):
    pipeline = DedupePipeline()
    job = make_job()
    assert pipeline.process_item(job, spider) is job
    with pytest.raises(DropItem):
        pipeline.process_item(make_job(), spider)
    assert spider.stats["jobs/dropped/duplicate"] == 1


def test_enrichissement_sans_greffon_est_transparent(spider):
    job = make_job()
    assert EnrichPipeline().process_item(job, spider) is job


def test_un_enrichisseur_defaillant_ne_bloque_pas(spider):
    """Une offre non enrichie reste exploitable ; une collecte interrompue, non."""
    class Casse:
        name = "casse"
        def enrich(self, item):
            raise RuntimeError("boum")

    pipeline = EnrichPipeline()
    pipeline.enrichers = [Casse()]
    job = make_job()
    assert pipeline.process_item(job, spider) is job
    assert spider.stats["jobs/enrich_failed/casse"] == 1


def test_html_spider_s_arrete_sur_une_page_vide():
    """Une page de resultats sans annonce marque la fin : inutile d'insister."""
    from jobs_scrape.spiders import HtmlJobSpider
    from jobs_scrape.testing import html_response

    class Spider(HtmlJobSpider):
        name = "demo"
        detail_url_re = r"/offre/"
        next_page_css = "a.next::attr(href)"

    spider = Spider()
    vide = html_response("https://x.test/liste?page=9", '<a class="next" href="?page=10">→</a>')
    assert list(spider.parse_listing(vide)) == []

    pleine = html_response(
        "https://x.test/liste?page=1",
        '<a href="/offre/1">a</a><a class="next" href="?page=2">→</a>',
    )
    urls = [r.url for r in spider.parse_listing(pleine)]
    assert "https://x.test/offre/1" in urls
    assert "https://x.test/liste?page=2" in urls


def test_next_page_url_redefinissable():
    """Les sites qui paginent par parametre d'URL redefinissent ce seul point."""
    from jobs_scrape.spiders import HtmlJobSpider
    from jobs_scrape.testing import html_response

    class Spider(HtmlJobSpider):
        name = "demo2"
        detail_url_re = r"/offre/"

        def next_page_url(self, response, page):
            return f"https://x.test/liste?page={page + 1}"

    spider = Spider()
    page = html_response("https://x.test/liste", '<a href="/offre/1">a</a>')
    urls = [r.url for r in spider.parse_listing(page)]
    assert "https://x.test/liste?page=2" in urls
