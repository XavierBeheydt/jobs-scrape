"""Extraction JSON-LD, verifiee sur une page jobup.ch reelle et figee."""

from pathlib import Path

import pytest

from jobs_scrape import jsonld
from jobs_scrape.testing import html_response

FIXTURE = Path(__file__).parent / "fixtures" / "jobup_detail.html"
URL = "https://www.jobup.ch/fr/emplois/detail/2acc13b6-cd64-4353-9cd7-892faf540f74/"


@pytest.fixture
def fields():
    response = html_response(URL, FIXTURE.read_bytes())
    posting = jsonld.find_jobposting(response)
    assert posting is not None, "aucun JobPosting dans la fixture"
    return jsonld.to_fields(posting, url=URL)


def test_champs_principaux(fields):
    assert fields["title"] == "Team Lead – Développement/Intégration"
    assert fields["company"] == "FHV Informatique"
    assert fields["external_id"] == "2acc13b6-cd64-4353-9cd7-892faf540f74"
    # Valeur brute : "2026-08-07T02:02:37+02:00", soit le 7 aout.
    # Cette assertion figeait auparavant 2026-07-08, resultat d'un defaut de
    # lecture des dates ISO -- un mois d'ecart, passe inapercu.
    assert fields["posted_at"] == "2026-08-07"


def test_localisation(fields):
    """jobup range la ville dans addressRegion : on doit quand meme la retrouver."""
    assert fields["city"] == "Prilly"
    assert fields["postal_code"] == "1008"
    assert fields["country"] == "CH"


def test_type_de_contrat_francais(fields):
    """« duree indeterminee » n'existe pas dans schema.org, mais doit etre compris."""
    assert fields["contract_type"] == "permanent"


def test_salaire_vide_non_retourne(fields):
    """jobup declare baseSalary sans montant : ne rien produire vaut mieux qu'un zero."""
    assert "salary_min" not in fields


def test_page_sans_jsonld():
    assert jsonld.find_jobposting(html_response("https://x.test", "<html></html>")) is None


def test_jsonld_invalide_est_ignore():
    body = '<script type="application/ld+json">{ceci n est pas du json}</script>'
    assert jsonld.find_jobposting(html_response("https://x.test", body)) is None


def test_enveloppe_graph():
    body = (
        '<script type="application/ld+json">'
        '{"@graph":[{"@type":"WebPage"},{"@type":"JobPosting","title":"Testeur"}]}'
        "</script>"
    )
    posting = jsonld.find_jobposting(html_response("https://x.test", body))
    assert posting and posting["title"] == "Testeur"
