"""Processors de normalisation, partages par tous les modules de collecte.

Chaque source livre ses champs dans son propre format ; ces fonctions les
ramenent au format commun attendu par :class:`~jobs_scrape.items.JobItem`.

Elles sont volontairement tolerantes : une valeur qu'on ne sait pas interpreter
renvoie ``None`` plutot que de faire echouer la collecte d'une offre par
ailleurs exploitable. Perdre un salaire mal formate est preferable a perdre
l'annonce entiere.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime

from dateutil import parser as date_parser
from w3lib.html import remove_tags, replace_entities

__all__ = [
    "clean_text",
    "html_to_text",
    "to_iso_date",
    "to_float",
    "to_int",
    "parse_workload",
    "parse_salary",
    "normalize_country",
    "utc_now_iso",
    "slugify",
]

# Espaces exotiques rencontres dans les annonces : fine insecable (typographie
# francaise), insecable (HTML), et l'apostrophe suisse de milliers.
_SPACE_CHARS = "    "
_WS_RE = re.compile(r"\s+")


def clean_text(value: str | None) -> str | None:
    """Nettoie une chaine : entites HTML, espaces exotiques, blancs multiples."""
    if value is None:
        return None
    text = replace_entities(str(value))
    for ch in _SPACE_CHARS:
        text = text.replace(ch, " ")
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def html_to_text(value: str | None) -> str | None:
    """Convertit un fragment HTML en texte lisible, en gardant les sauts de bloc.

    Les descriptions d'offres sont structurees en listes et paragraphes ; tout
    aplatir sur une ligne rendrait le texte illisible et degraderait la qualite
    de l'extraction de mots-cles. On preserve donc les ruptures de bloc.
    """
    if value is None:
        return None
    text = str(value)
    text = re.sub(r"(?i)<\s*br\s*/?\s*>", "\n", text)
    text = re.sub(r"(?i)</\s*(p|div|li|tr|h[1-6])\s*>", "\n", text)
    text = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", text)
    text = remove_tags(text)
    text = replace_entities(text)
    for ch in _SPACE_CHARS:
        text = text.replace(ch, " ")
    lines = [_WS_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or None


def to_iso_date(value: str | date | datetime | None) -> str | None:
    """Ramene une date a la forme ISO ``AAAA-MM-JJ``.

    L'ordre des tentatives est essentiel. On essaie **d'abord** la lecture
    ISO 8601 stricte, avant toute interpretation heuristique.

    La raison : ``dateutil`` avec ``dayfirst=True`` -- necessaire pour lire le
    ``21/08/2026`` francais -- se trompe sur une date deja ISO des que le jour
    et le mois sont tous deux inferieurs a 13. ``"2026-07-02"`` devenait ainsi
    le 7 fevrier au lieu du 2 juillet. Le defaut etait silencieux et touchait
    environ un tiers des dates, sur toutes les sources renvoyant de l'ISO --
    c'est-a-dire la plupart des API.

    L'heuristique ``dayfirst`` ne sert donc que de repli, pour les formats
    reellement ambigus ecrits a la francaise.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = clean_text(value)
    if not text:
        return None

    # 1. ISO 8601, sans aucune interpretation. Couvre "2026-07-02",
    #    "2026-07-02T10:29:35" et les variantes avec fuseau.
    candidate = text.replace("Z", "+00:00") if text.endswith("Z") else text
    for parser in (datetime.fromisoformat, date.fromisoformat):
        try:
            parsed = parser(candidate)
        except (ValueError, TypeError):
            continue
        return parsed.date().isoformat() if isinstance(parsed, datetime) else parsed.isoformat()

    # 2. Repli heuristique : formats libres, jour en premier (usage FR/CH).
    try:
        return date_parser.parse(text, dayfirst=True).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _to_number(raw: str) -> float | None:
    """Interprete un nombre ecrit a la francaise ou a la suisse.

    Gere ``80'000`` (Suisse), ``80 000`` et ``80.000`` (France), ainsi que la
    virgule decimale. La regle : un dernier separateur suivi de un ou deux
    chiffres est une decimale, tout le reste est un separateur de milliers.
    """
    text = raw.strip()
    for ch in _SPACE_CHARS + " '’":
        text = text.replace(ch, "")
    if not text:
        return None

    match = re.search(r"[.,](\d{1,2})$", text)
    if match:
        head = text[: match.start()].replace(".", "").replace(",", "")
        text = f"{head}.{match.group(1)}"
    else:
        text = text.replace(".", "").replace(",", "")

    try:
        return float(text)
    except ValueError:
        return None


def to_float(value: object) -> float | None:
    """Extrait un nombre decimal d'une valeur quelconque.

    Une chaine deja ecrite en notation standard est lue telle quelle,
    **avant** toute heuristique de separateurs. C'est indispensable pour les
    valeurs venant d'API JSON : une latitude ``"47.405"`` vaut 47,405 degres,
    et l'heuristique monetaire -- qui ne reconnait comme decimale qu'un
    separateur suivi d'un ou deux chiffres -- la transformerait en 47 405.

    Contrepartie assumee : ``"80.000"`` ecrit a la francaise pour 80 000 sera
    lu 80,0. Les montants en texte libre passent par :func:`parse_salary`, qui
    applique bien l'heuristique de milliers ; cette fonction-ci sert d'abord
    aux nombres deja structures.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass

    match = re.search(r"-?\d[\d\s.,'  ’]*", text)
    return _to_number(match.group(0)) if match else None


def to_int(value: object) -> int | None:
    """Extrait un entier d'une valeur quelconque."""
    number = to_float(value)
    return int(round(number)) if number is not None else None


def parse_workload(value: object) -> tuple[int | None, int | None]:
    """Lit un taux d'activite et renvoie ``(minimum, maximum)`` en pourcent.

    Couvre ``"100%"``, ``"80 - 100%"``, ``"80%-100%"`` et les entiers bruts.
    Une valeur unique remplit les deux bornes : un poste a 100 % a bien pour
    minimum et maximum 100.
    """
    if value is None:
        return None, None
    if isinstance(value, (int, float)):
        pct = int(round(float(value)))
        return pct, pct

    text = clean_text(str(value)) or ""
    numbers = [int(n) for n in re.findall(r"\d{1,3}", text)]
    numbers = [n for n in numbers if 0 <= n <= 100]
    if not numbers:
        return None, None
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return min(numbers), max(numbers)


# Indices qu'un texte parle bien de remuneration. Sans devise ni l'un de ces
# mots, on refuse d'interpreter les nombres qu'il contient.
_SALARY_KEYWORDS = re.compile(
    r"\bsalaire|\bsalarial|\bremuneration|\brémunération|\bbrut\b|\bnet\b"
    r"|\bannuel|\bmensuel|\bpar an\b|\bpar mois\b"
    r"|\bgehalt|\blohn\b|\bjahresgehalt|\bsalary\b|\bcompensation\b",
    re.I,
)

_CURRENCIES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bCHF\b|\bFr\.|\bfrs\b", re.I), "CHF"),
    (re.compile(r"€|\bEUR\b|\beuros?\b", re.I), "EUR"),
    (re.compile(r"\bGBP\b|£", re.I), "GBP"),
    (re.compile(r"\bUSD\b|\$", re.I), "USD"),
)


def parse_salary(
    value: str | None, currency_hint: str | None = None
) -> tuple[float | None, float | None, str | None]:
    """Lit une mention de salaire en texte libre.

    Renvoie ``(minimum, maximum, devise)``. Reconnait ``"36 - 42 k€ brut annuel"``
    (APEC), ``"CHF 80'000 - 100'000"`` (Suisse) et les montants uniques ; le
    suffixe ``k`` multiplie par mille.

    **Une devise ou un mot-cle de remuneration est exige.** Sans ce garde-fou,
    une phrase comme « poste ouvert en 2026 » produirait un salaire de 2026 :
    n'importe quel nombre a quatre chiffres ressemble a un montant. Les modules
    qui connaissent la devise par le contexte -- une API qui la donne dans un
    champ voisin -- la passent via ``currency_hint``.

    Renvoyer trois ``None`` est un resultat courant et normal : la plupart des
    annonces ne chiffrent pas la remuneration.
    """
    if not value:
        return None, None, None
    text = clean_text(str(value))
    if not text:
        return None, None, None

    currency = currency_hint
    for pattern, code in _CURRENCIES:
        if pattern.search(text):
            currency = code
            break

    has_keyword = bool(_SALARY_KEYWORDS.search(text))
    if not currency and not has_keyword:
        return None, None, None

    # Un « k » colle au nombre ou separe par un espace vaut multiplication par mille.
    multiplier = 1000.0 if re.search(r"\d\s*[kK]\b|\d\s*[kK][€$]", text) else 1.0

    amounts: list[float] = []
    for raw in re.findall(r"\d[\d\s.,'\u202f\u00a0\u2019]*", text):
        number = _to_number(raw)
        if number is None:
            continue
        # Une annee ecrite telle quelle -- quatre chiffres sans separateur, dans
        # une plage plausible -- n'est pas un montant.
        if multiplier == 1.0 and re.fullmatch(r"\d{4}", raw.strip()) and 1900 <= number <= 2100:
            continue
        amounts.append(number * multiplier)

    # Sous mille, c'est un taux d'activite, un nombre de postes ou un numero.
    amounts = [a for a in amounts if a >= 1000]
    if not amounts:
        return None, None, currency
    if len(amounts) == 1:
        return amounts[0], amounts[0], currency
    return min(amounts), max(amounts), currency


_COUNTRY_ALIASES = {
    "ch": "CH", "suisse": "CH", "schweiz": "CH", "svizzera": "CH", "switzerland": "CH",
    "fr": "FR", "france": "FR",
    "de": "DE", "allemagne": "DE", "deutschland": "DE", "germany": "DE",
    "be": "BE", "belgique": "BE", "belgium": "BE",
    "lu": "LU", "luxembourg": "LU",
    "it": "IT", "italie": "IT", "italy": "IT",
}


def normalize_country(value: str | None) -> str | None:
    """Ramene un nom de pays a son code ISO 3166-1 alpha-2."""
    text = clean_text(value)
    if not text:
        return None
    key = unicodedata.normalize("NFKD", text.lower())
    key = "".join(c for c in key if not unicodedata.combining(c)).strip(" .")
    if key in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[key]
    return text.upper() if len(text) == 2 else None


def utc_now_iso() -> str:
    """Horodatage UTC courant, en ISO 8601 avec suffixe ``Z``."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def slugify(value: str) -> str:
    """Identifiant stable en minuscules, sans accent ni ponctuation."""
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
