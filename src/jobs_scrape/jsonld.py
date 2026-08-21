"""Lecture des blocs JSON-LD ``JobPosting`` embarques dans les pages.

Beaucoup de sites d'emploi publient leurs annonces au format schema.org pour
apparaitre dans Google for Jobs. C'est une aubaine : ces donnees sont
structurees, documentees, et bien plus stables que des selecteurs CSS -- elles
survivent aux refontes graphiques, qui cassent tout le reste.

Deux modules du projet s'appuient dessus : ``jobup`` et le collecteur generique
des agences genevoises, qui couvre des dizaines de sites d'un seul parseur.

Le code ci-dessous est defensif a dessein. Le balisage rencontre dans la nature
s'ecarte souvent de la specification : champs absents, types incoherents
(chaine la ou un objet est attendu), listes la ou un scalaire est prevu,
enveloppes ``@graph``. Chaque acces tolere ces variantes.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from jobs_scrape.loaders import (
    clean_text,
    html_to_text,
    normalize_country,
    to_float,
    to_iso_date,
)

_JSONLD_XPATH = '//script[@type="application/ld+json"]/text()'

# Vocabulaire schema.org des types de contrat, ramene a nos valeurs internes.
_EMPLOYMENT_TYPES = {
    "full_time": "full_time",
    "part_time": "part_time",
    "contractor": "contractor",
    "temporary": "temporary",
    "intern": "internship",
    "volunteer": "volunteer",
    "per_diem": "per_diem",
    "other": "other",
}

# En pratique, les sites suisses et francais ignorent largement le vocabulaire
# anglais de schema.org et y placent leur propre libelle. jobup.ch annonce ainsi
# « duree indeterminee ». Sans ces equivalences, chaque site produirait sa
# propre valeur et le champ deviendrait inexploitable pour filtrer.
_EMPLOYMENT_ALIASES = {
    "duree indeterminee": "permanent",
    "contrat a duree indeterminee": "permanent",
    "cdi": "permanent",
    "unbefristet": "permanent",
    "festanstellung": "permanent",
    "permanent": "permanent",
    "duree determinee": "fixed_term",
    "contrat a duree determinee": "fixed_term",
    "cdd": "fixed_term",
    "befristet": "fixed_term",
    "temps plein": "full_time",
    "plein temps": "full_time",
    "vollzeit": "full_time",
    "temps partiel": "part_time",
    "teilzeit": "part_time",
    "stage": "internship",
    "praktikum": "internship",
    "internship": "internship",
    "apprentissage": "apprenticeship",
    "lehrstelle": "apprenticeship",
    "apprentissage dual": "apprenticeship",
    "temporaire": "temporary",
    "interim": "temporary",
    "mission temporaire": "temporary",
    "freelance": "contractor",
    "independant": "contractor",
    "selbstandig": "contractor",
}


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _text(value: Any) -> str | None:
    """Extrait du texte d'une valeur qui peut etre chaine, objet ou liste.

    schema.org autorise ``"CH"``, ``{"@type": "Country", "name": "CH"}`` et
    ``[{...}]`` pour exprimer la meme chose. Les trois passent ici.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return clean_text(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("name", "value", "@value", "text"):
            if key in value:
                return _text(value[key])
        return None
    if isinstance(value, list):
        for entry in value:
            found = _text(entry)
            if found:
                return found
    return None


def extract_blocks(response) -> list[dict]:
    """Tous les objets JSON-LD d'une page, enveloppes ``@graph`` deroulees."""
    blocks: list[dict] = []
    for raw in response.xpath(_JSONLD_XPATH).getall():
        try:
            parsed = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            # Du JSON-LD invalide est frequent et sans gravite : on passe.
            continue
        for entry in _as_list(parsed):
            if not isinstance(entry, dict):
                continue
            if "@graph" in entry:
                blocks.extend(e for e in _as_list(entry["@graph"]) if isinstance(e, dict))
            else:
                blocks.append(entry)
    return blocks


def find_jobposting(response) -> dict | None:
    """Le premier bloc ``JobPosting`` de la page, s'il y en a un."""
    for block in extract_blocks(response):
        types = {str(t) for t in _as_list(block.get("@type"))}
        if "JobPosting" in types:
            return block
    return None


def _parse_location(posting: dict) -> dict[str, Any]:
    places = _as_list(posting.get("jobLocation"))
    for place in places:
        if not isinstance(place, dict):
            continue
        address = place.get("address")
        if isinstance(address, list):
            address = next((a for a in address if isinstance(a, dict)), None)
        if not isinstance(address, dict):
            continue

        locality = _text(address.get("addressLocality"))
        region = _text(address.get("addressRegion"))
        # Certains sites -- jobup notamment -- rangent la ville dans
        # ``addressRegion`` et laissent ``addressLocality`` vide. On accepte
        # l'un pour l'autre plutot que de perdre la localisation.
        fields: dict[str, Any] = {
            "city": locality or region,
            "region": region if locality else None,
            "postal_code": _text(address.get("postalCode")),
            "country": normalize_country(_text(address.get("addressCountry"))),
        }
        parts = [
            _text(address.get("streetAddress")),
            fields["postal_code"],
            fields["city"],
        ]
        fields["location_raw"] = ", ".join(p for p in parts if p) or None

        geo = place.get("geo")
        if isinstance(geo, dict):
            fields["lat"] = to_float(geo.get("latitude"))
            fields["lon"] = to_float(geo.get("longitude"))
        return fields
    return {}


def _parse_salary(posting: dict) -> dict[str, Any]:
    salary = posting.get("baseSalary")
    if isinstance(salary, list):
        salary = next((s for s in salary if isinstance(s, dict)), None)
    if not isinstance(salary, dict):
        return {}

    currency = _text(salary.get("currency")) or _text(salary.get("currencyCode"))
    amount = salary.get("value")
    if isinstance(amount, list):
        amount = next((v for v in amount if isinstance(v, dict)), None)

    low = high = None
    if isinstance(amount, dict):
        low = to_float(amount.get("minValue"))
        high = to_float(amount.get("maxValue"))
        single = to_float(amount.get("value"))
        if low is None and high is None and single is not None:
            low = high = single
    elif amount is not None:
        low = high = to_float(amount)

    if low is None and high is None:
        # Un bloc ``baseSalary`` vide est courant : le site declare la structure
        # sans renseigner de montant. La devise seule n'a pas d'interet.
        return {}
    return {"salary_min": low, "salary_max": high, "salary_currency": currency}


def _normalize_key(value: str) -> str:
    """Cle de comparaison : minuscules, sans accent, separateurs unifies."""
    text = unicodedata.normalize("NFKD", str(value).strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[\s_-]+", " ", text).strip()


def _parse_employment_type(posting: dict) -> str | None:
    """Ramene un type de contrat a une valeur interne stable.

    On interroge d'abord le vocabulaire schema.org, puis les libelles francais
    et allemands rencontres sur les sites suisses. En dernier recours on rend la
    valeur normalisee telle quelle : mieux vaut un libelle brut exploitable a
    l'oeil qu'un champ vide.
    """
    for raw in _as_list(posting.get("employmentType")):
        if not raw:
            continue
        key = _normalize_key(raw)
        if key in _EMPLOYMENT_ALIASES:
            return _EMPLOYMENT_ALIASES[key]
        underscored = key.replace(" ", "_")
        if underscored in _EMPLOYMENT_TYPES:
            return _EMPLOYMENT_TYPES[underscored]
        return underscored or None
    return None


def _parse_identifier(posting: dict) -> str | None:
    identifier = posting.get("identifier")
    if isinstance(identifier, dict):
        return _text(identifier.get("value")) or _text(identifier.get("name"))
    return _text(identifier)


def to_fields(posting: dict, url: str | None = None) -> dict[str, Any]:
    """Traduit un ``JobPosting`` schema.org en champs de ``JobItem``.

    Seules les cles reellement renseignees sont renvoyees : l'appelant peut donc
    fusionner ce dictionnaire par-dessus des valeurs deja extraites du HTML sans
    craindre de les ecraser avec des ``None``.
    """
    fields: dict[str, Any] = {
        "title": _text(posting.get("title")),
        "description": html_to_text(posting.get("description")),
        "external_id": _parse_identifier(posting),
        "url": _text(posting.get("url")) or url,
        "posted_at": to_iso_date(_text(posting.get("datePosted"))),
        "expires_at": to_iso_date(_text(posting.get("validThrough"))),
        "contract_type": _parse_employment_type(posting),
        "apply_url": _text(posting.get("url")) or url,
    }

    organisation = posting.get("hiringOrganization")
    if isinstance(organisation, list):
        organisation = next((o for o in organisation if isinstance(o, dict)), None)
    if isinstance(organisation, dict):
        fields["company"] = _text(organisation.get("name"))
    elif organisation:
        fields["company"] = _text(organisation)

    location_types = {str(v).upper() for v in _as_list(posting.get("jobLocationType"))}
    if "TELECOMMUTE" in location_types:
        fields["remote_policy"] = "remote"

    fields.update(_parse_location(posting))
    fields.update(_parse_salary(posting))

    return {k: v for k, v in fields.items() if v not in (None, "", [], {})}
