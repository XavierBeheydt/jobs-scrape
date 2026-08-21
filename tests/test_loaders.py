"""Les processors doivent absorber ce que les sources FR/CH ecrivent reellement."""

import pytest

from jobs_scrape.loaders import (
    clean_text,
    html_to_text,
    normalize_country,
    parse_salary,
    parse_workload,
    slugify,
    to_int,
    to_iso_date,
)


@pytest.mark.parametrize("raw,expected", [
    ("36 - 42 k€ brut annuel", (36000.0, 42000.0, "EUR")),
    ("CHF 80'000 - 100'000", (80000.0, 100000.0, "CHF")),      # apostrophe suisse
    ("Salaire : 55 000 € par an", (55000.0, 55000.0, "EUR")),  # espace francais
    ("entre 90'000 et 120'000 CHF", (90000.0, 120000.0, "CHF")),
    ("selon experience", (None, None, None)),
    ("", (None, None, None)),
    (None, (None, None, None)),
])
def test_parse_salary(raw, expected):
    assert parse_salary(raw) == expected


def test_parse_salary_ignore_les_nombres_trop_petits():
    """2026 est une annee, 100 un pourcentage : ni l'un ni l'autre n'est un salaire."""
    assert parse_salary("Poste ouvert en 2026, taux 100%") == (None, None, None)


@pytest.mark.parametrize("raw,expected", [
    ("100%", (100, 100)), ("80 - 100%", (80, 100)), ("60%-80%", (60, 80)),
    (100, (100, 100)), ("plein temps", (None, None)), (None, (None, None)),
])
def test_parse_workload(raw, expected):
    assert parse_workload(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2026-08-21T10:29:35.000+0000", "2026-08-21"),
    ("21/08/2026", "2026-08-21"),          # format francais, pas americain
    ("2026-08-21", "2026-08-21"),
    ("n'importe quoi", None),
    (None, None),
])
def test_to_iso_date(raw, expected):
    assert to_iso_date(raw) == expected


def test_html_to_text_preserve_la_structure():
    """Les listes portent le sens d'une annonce : les aplatir nuirait a l'extraction."""
    out = html_to_text("<p>Missions</p><ul><li>Piloter&nbsp;le projet</li><li>Encadrer</li></ul>")
    assert out == "Missions\n- Piloter le projet\n- Encadrer"


def test_clean_text_normalise_les_espaces_exotiques():
    assert clean_text("Chef de projet  ") == "Chef de projet"


@pytest.mark.parametrize("raw,expected", [
    ("Suisse", "CH"), ("suisse", "CH"), ("Schweiz", "CH"),
    ("France", "FR"), ("CH", "CH"), ("Zimbabwe", None), (None, None),
])
def test_normalize_country(raw, expected):
    assert normalize_country(raw) == expected


def test_to_int_et_slugify():
    assert to_int("1 234") == 1234
    assert slugify("Développeur Full-Stack (H/F)") == "developpeur-full-stack-h-f"


@pytest.mark.parametrize("raw,expected", [
    ("47.405", 47.405),      # latitude : trois decimales, pas un separateur de milliers
    ("8.484", 8.484),
    ("47.2", 47.2),
    ("-1.5", -1.5),
    ("80'000", 80000.0),     # apostrophe suisse : bien un separateur de milliers
    ("1 234", 1234.0),
    ("55,5", 55.5),
    ("CHF 1'250.50", 1250.50),
])
def test_to_float_lit_les_coordonnees_sans_les_deformer(raw, expected):
    """Regression : l'heuristique monetaire transformait 47.405 en 47405."""
    from jobs_scrape.loaders import to_float

    assert to_float(raw) == pytest.approx(expected)
