"""Recherche : classement, facettes, et robustesse a la saisie libre."""

import pytest
from conftest import make_job

from jobs_scrape import search, storage


@pytest.fixture
def corpus(db):
    jobs = [
        make_job(external_id="1", url="https://a/1", title="Développeur Python senior",
                 company="ACME SA", city="Genève", region="GE",
                 description="Django, PostgreSQL, Kubernetes.",
                 skills=["python", "django"], workload_min=80, workload_max=100),
        make_job(external_id="2", url="https://a/2", title="Data Engineer",
                 company="Banque XY", city="Zürich", region="ZH",
                 description="Python, Spark et Airflow au quotidien.",
                 skills=["python", "spark"], workload_min=100, workload_max=100),
        make_job(external_id="3", url="https://b/3", title="Chef de projet",
                 source="apec", company="Conseil", city="Lyon", region="69",
                 country="FR", description="Pilotage, methode agile.",
                 skills=["agile"], workload_min=None, workload_max=None),
    ]
    for job in jobs:
        storage.upsert(db, job)
    db.commit()
    return db


def test_recherche_sans_accent_trouve_le_texte_accentue(corpus):
    """Indispensable sur un corpus francophone : personne ne tape les accents."""
    assert len(search.search(corpus, "developpeur")) == 1


def test_la_ville_est_dans_le_plein_texte(corpus):
    """On cherche un emploi par « quoi ET ou », dans un seul champ de saisie."""
    assert len(search.search(corpus, "geneve")) == 1


def test_le_titre_pese_plus_que_la_description(corpus):
    """« Developpeur Python » doit devancer une annonce qui cite Python en passant."""
    results = search.search(corpus, "python")
    assert results[0]["title"] == "Développeur Python senior"


def test_prefixe(corpus):
    assert len(search.search(corpus, "develop*")) == 1


def test_sans_requete_les_plus_recentes(corpus):
    assert len(search.search(corpus, None)) == 3


@pytest.mark.parametrize("query", [
    'python "data engineer"', "c++ (dev)", 'guillemet " seul',
    "python AND spark", "*", "^^^", "NEAR(a b)", "'",
])
def test_saisie_hostile_ne_plante_pas(corpus, query):
    """La requete peut venir d'un humain ou d'un modele : jamais de confiance."""
    search.search(corpus, query)


def test_filtre_competences_cumulatif(corpus):
    assert len(search.search(corpus, None, skills=["python"])) == 2
    assert len(search.search(corpus, None, skills=["python", "spark"])) == 1
    assert len(search.search(corpus, None, skills=["python", "cobol"])) == 0


def test_filtre_taux_compare_au_maximum(corpus):
    """Un poste 80-100 % convient a qui cherche 90 %."""
    assert len(search.search(corpus, None, workload_min=90)) == 2


def test_filtres_combines(corpus):
    assert len(search.search(corpus, "python", region="ZH")) == 1
    assert len(search.search(corpus, "python", region="GE")) == 1
    assert len(search.search(corpus, "python", source="apec")) == 0


def test_count_suit_les_filtres(corpus):
    assert search.count(corpus, "python") == 2
    assert search.count(corpus, None, country="FR") == 1


def test_facettes(corpus):
    assert {f["value"] for f in search.facets(corpus, "region")} == {"GE", "ZH", "69"}
    with pytest.raises(ValueError):
        search.facets(corpus, "colonne_inexistante")


def test_top_terms(corpus):
    top = search.top_terms(corpus, "skills", limit=3)
    assert top[0] == {"value": "python", "count": 2}


def test_summary(corpus):
    data = search.summary(corpus)
    assert data["total"] == 3
    assert data["sources"] == 2
