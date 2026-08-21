"""Normalisation : ramene chaque offre au format commun."""

from __future__ import annotations

from dataclasses import fields as dataclass_fields

from jobs_scrape.items import LIST_FIELDS, JobItem, compute_fingerprint
from jobs_scrape.loaders import (
    clean_text,
    normalize_country,
    to_float,
    to_int,
    to_iso_date,
    utc_now_iso,
)

_TEXT_FIELDS = (
    "source", "external_id", "url", "title", "company", "location_raw",
    "city", "postal_code", "region", "contract_type", "seniority",
    "remote_policy", "apply_url", "lang",
)


class NormalizePipeline:
    """Uniformise les champs et calcule l'empreinte de deduplication.

    Les modules ont le droit d'etre approximatifs : renvoyer une date au format
    du site, un taux d'activite en chaine, un pays en toutes lettres. C'est ici
    que tout est ramene a une forme unique -- sans quoi la deduplication, les
    filtres et les tris ne voudraient rien dire.
    """

    _allowed = {f.name for f in dataclass_fields(JobItem)}

    def process_item(self, item, spider):
        if isinstance(item, dict):
            # Un module peut renvoyer un dictionnaire ; on ignore les cles
            # inconnues plutot que d'echouer sur une faute de frappe.
            item = JobItem(**{k: v for k, v in item.items() if k in self._allowed})

        for name in _TEXT_FIELDS:
            setattr(item, name, clean_text(getattr(item, name, None)))

        if item.description:
            # La description garde ses sauts de ligne : ils portent la structure
            # (missions, profil, avantages) et servent a l'extraction de mots-cles.
            item.description = "\n".join(
                line.strip() for line in str(item.description).splitlines()
            ).strip() or None

        item.country = normalize_country(item.country)
        item.posted_at = to_iso_date(item.posted_at)
        item.expires_at = to_iso_date(item.expires_at)
        item.scraped_at = item.scraped_at or utc_now_iso()

        item.lat = to_float(item.lat)
        item.lon = to_float(item.lon)
        item.salary_min = to_float(item.salary_min)
        item.salary_max = to_float(item.salary_max)
        item.salary_currency = (item.salary_currency or "").upper() or None

        item.workload_min = _clamp_percent(item.workload_min)
        item.workload_max = _clamp_percent(item.workload_max)
        if (
            item.workload_min is not None
            and item.workload_max is not None
            and item.workload_min > item.workload_max
        ):
            item.workload_min, item.workload_max = item.workload_max, item.workload_min

        for name in LIST_FIELDS:
            setattr(item, name, _clean_list(getattr(item, name, None)))

        item.fingerprint = item.fingerprint or compute_fingerprint(item)
        return item


def _clamp_percent(value) -> int | None:
    """Un taux d'activite hors de [0, 100] est une erreur de lecture, pas une donnee."""
    number = to_int(value)
    if number is None:
        return None
    return max(0, min(100, number))


def _clean_list(value) -> list[str]:
    """Liste de chaines nettoyees, sans doublon, ordre d'apparition conserve."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    seen: set[str] = set()
    result: list[str] = []
    for entry in value:
        text = clean_text(entry)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
