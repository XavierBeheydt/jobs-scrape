"""Schema normalise, partage par toutes les sources de collecte."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, fields


@dataclass
class JobItem:
    """Une offre d'emploi normalisee, quelle que soit sa provenance.

    Toutes les sources produisent ce meme objet : les pipelines, le stockage et la
    recherche n'ont donc qu'un seul schema a connaitre. Tous les champs sont
    optionnels a la construction ; seuls ``source``, ``url`` et ``title`` sont
    exiges par la validation, parce qu'une offre sans l'un des trois n'est ni
    identifiable ni consultable.
    """

    # -- identite ---------------------------------------------------------
    source: str | None = None
    external_id: str | None = None
    url: str | None = None
    fingerprint: str | None = None

    # -- contenu ----------------------------------------------------------
    title: str | None = None
    company: str | None = None
    description: str | None = None

    # -- localisation -----------------------------------------------------
    location_raw: str | None = None
    city: str | None = None
    postal_code: str | None = None
    region: str | None = None          # canton suisse ou departement francais
    country: str | None = None         # code ISO 3166-1 alpha-2
    lat: float | None = None
    lon: float | None = None

    # -- conditions -------------------------------------------------------
    contract_type: str | None = None
    workload_min: int | None = None    # taux d'activite en pourcent
    workload_max: int | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None

    # -- dates (ISO 8601, AAAA-MM-JJ) -------------------------------------
    posted_at: str | None = None
    expires_at: str | None = None
    scraped_at: str | None = None

    # -- enrichissement ---------------------------------------------------
    lang: str | None = None
    keywords: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    seniority: str | None = None
    remote_policy: str | None = None

    # -- complements ------------------------------------------------------
    languages: list[str] = field(default_factory=list)   # langues exigees
    occupations: list[str] = field(default_factory=list) # codes metier
    apply_url: str | None = None


FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in fields(JobItem))

LIST_FIELDS: frozenset[str] = frozenset(
    {"keywords", "skills", "languages", "occupations"}
)

REQUIRED_FIELDS: tuple[str, ...] = ("source", "url", "title")


def compute_fingerprint(item: JobItem) -> str:
    """Empreinte stable d'une offre : c'est la cle de deduplication.

    On privilegie ``external_id`` quand la source en fournit un, parce qu'il
    survit aux changements d'URL (parametres de suivi ajoutes, slug modifie,
    migration de domaine). L'URL ne sert que de repli.
    """
    source = (item.source or "").strip().lower()
    identifier = (item.external_id or "").strip() or (item.url or "").strip()
    return hashlib.sha1(f"{source}|{identifier}".encode()).hexdigest()
