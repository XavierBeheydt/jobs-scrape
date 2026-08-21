"""Interrogation du corpus collecte.

Cette couche vit dans le coeur parce que c'est lui qui possede le schema en
ecriture : garder lecture et ecriture cote a cote evite qu'elles derivent l'une
de l'autre. Le serveur MCP et l'interface web s'appuient tous deux dessus, sans
ecrire une ligne de SQL.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from jobs_scrape.storage import row_to_dict

# Ponderation BM25, dans l'ordre des colonnes de ``jobs_fts``.
# Une correspondance dans le titre pese bien plus qu'une occurrence noyee dans
# une description de trois mille signes : sans ce reglage, une annonce qui cite
# « Python » en passant devancerait un poste intitule « Developpeur Python ».
_BM25_WEIGHTS = (10.0, 3.0, 4.0, 1.0, 6.0, 8.0)  # title, company, city, description, keywords, skills

_FTS_SPECIALS = re.compile(r'[":^*(){}\[\]]')


def build_match(query: str) -> str:
    """Traduit une saisie libre en expression FTS5 sure.

    La syntaxe FTS5 a ses operateurs (``AND``, ``NEAR``, guillemets, parentheses) ;
    une apostrophe ou un deux-points suffit a produire une erreur de syntaxe.
    Comme la saisie vient d'un humain -- ou d'un modele -- on ne lui fait pas
    confiance : chaque terme est neutralise puis mis entre guillemets.

    Deux facilites sont conservees parce qu'elles sont attendues : les groupes
    entre guillemets restent des expressions exactes, et un ``*`` final reste un
    prefixe (``develop*`` trouve « developpeur » et « developpement »).
    """
    tokens = re.findall(r'"[^"]*"|\S+', query or "")
    parts: list[str] = []
    for token in tokens:
        if token.startswith('"') and token.endswith('"') and len(token) > 2:
            inner = _FTS_SPECIALS.sub(" ", token[1:-1]).strip()
            if inner:
                parts.append(f'"{inner}"')
            continue
        prefix = token.endswith("*")
        cleaned = _FTS_SPECIALS.sub(" ", token).strip()
        if not cleaned:
            continue
        if cleaned.upper() in {"AND", "OR", "NOT"}:
            parts.append(cleaned.upper())
            continue
        parts.append(f'"{cleaned}"*' if prefix else f'"{cleaned}"')
    return " ".join(parts)


def _filters(
    *,
    source: str | None = None,
    region: str | None = None,
    city: str | None = None,
    company: str | None = None,
    country: str | None = None,
    contract_type: str | None = None,
    remote_policy: str | None = None,
    skills: list[str] | None = None,
    workload_min: int | None = None,
    salary_min: float | None = None,
    posted_since: str | None = None,
    lang: str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Construit les clauses ``WHERE`` communes a toutes les requetes."""
    clauses: list[str] = []
    params: dict[str, Any] = {}

    simple = {
        "source": source, "region": region, "country": country,
        "contract_type": contract_type, "remote_policy": remote_policy, "lang": lang,
    }
    for column, value in simple.items():
        if value:
            clauses.append(f"j.{column} = :{column}")
            params[column] = value

    # Ville et entreprise sont saisies a la main : on tolere la casse et le partiel.
    for column, value in (("city", city), ("company", company)):
        if value:
            clauses.append(f"j.{column} LIKE :{column}")
            params[column] = f"%{value}%"

    if workload_min is not None:
        # Un poste 60-100 % convient a qui cherche 80 % : on compare au maximum.
        clauses.append("COALESCE(j.workload_max, j.workload_min) >= :workload_min")
        params["workload_min"] = workload_min

    if salary_min is not None:
        clauses.append("COALESCE(j.salary_max, j.salary_min) >= :salary_min")
        params["salary_min"] = salary_min

    if posted_since:
        clauses.append("COALESCE(j.posted_at, j.first_seen_at) >= :posted_since")
        params["posted_since"] = posted_since

    if skills:
        # Toutes les competences demandees doivent etre presentes.
        for index, skill in enumerate(skills):
            key = f"skill_{index}"
            clauses.append(
                f"EXISTS (SELECT 1 FROM json_each(j.skills) s WHERE s.value = :{key})"
            )
            params[key] = skill

    return clauses, params


def search(
    conn: sqlite3.Connection,
    query: str | None = None,
    *,
    limit: int = 20,
    offset: int = 0,
    **filters: Any,
) -> list[dict[str, Any]]:
    """Recherche plein-texte classee par pertinence, avec filtres a facettes.

    Sans terme de recherche, renvoie les offres les plus recentes correspondant
    aux filtres -- ce qui rend l'appel utile pour naviguer autant que pour chercher.
    """
    clauses, params = _filters(**filters)
    params["limit"] = limit
    params["offset"] = offset

    match = build_match(query) if query else ""
    if match:
        params["match"] = match
        weights = ", ".join(str(w) for w in _BM25_WEIGHTS)
        where = " AND ".join(["f.jobs_fts MATCH :match", *clauses])
        sql = f"""
            SELECT j.*, bm25(jobs_fts, {weights}) AS rank
            FROM jobs_fts f
            JOIN jobs j ON j.rowid = f.rowid
            WHERE {where}
            ORDER BY rank
            LIMIT :limit OFFSET :offset
        """
    else:
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT j.*, NULL AS rank
            FROM jobs j{where}
            ORDER BY COALESCE(j.posted_at, j.first_seen_at) DESC
            LIMIT :limit OFFSET :offset
        """
    return [row_to_dict(row) for row in conn.execute(sql, params)]


def count(conn: sqlite3.Connection, query: str | None = None, **filters: Any) -> int:
    """Nombre total de resultats, pour la pagination."""
    clauses, params = _filters(**filters)
    match = build_match(query) if query else ""
    if match:
        params["match"] = match
        where = " AND ".join(["f.jobs_fts MATCH :match", *clauses])
        sql = f"SELECT COUNT(*) AS n FROM jobs_fts f JOIN jobs j ON j.rowid=f.rowid WHERE {where}"
    else:
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT COUNT(*) AS n FROM jobs j{where}"
    return conn.execute(sql, params).fetchone()["n"]


_FACET_COLUMNS = {
    "source", "region", "city", "company", "country",
    "contract_type", "remote_policy", "lang", "seniority",
}


def facets(
    conn: sqlite3.Connection, field: str, *, limit: int = 30, **filters: Any
) -> list[dict[str, Any]]:
    """Valeurs distinctes d'un champ et leur effectif."""
    if field not in _FACET_COLUMNS:
        allowed = ", ".join(sorted(_FACET_COLUMNS))
        raise ValueError(f"facette '{field}' inconnue. Disponibles : {allowed}")

    clauses, params = _filters(**filters)
    clauses.append(f"j.{field} IS NOT NULL AND j.{field} != ''")
    params["limit"] = limit
    where = " AND ".join(clauses)
    sql = f"""
        SELECT j.{field} AS value, COUNT(*) AS count
        FROM jobs j WHERE {where}
        GROUP BY j.{field} ORDER BY count DESC, value LIMIT :limit
    """
    return [dict(row) for row in conn.execute(sql, params)]


def top_terms(
    conn: sqlite3.Connection, field: str = "skills", *, limit: int = 30, **filters: Any
) -> list[dict[str, Any]]:
    """Mots-cles ou competences les plus frequents.

    Ces champs sont stockes en tableaux JSON ; ``json_each`` les deplie, ce qui
    evite d'avoir a maintenir une table d'association a cote.
    """
    if field not in {"skills", "keywords", "languages", "occupations"}:
        raise ValueError(f"champ '{field}' non deployable en termes")

    clauses, params = _filters(**filters)
    params["limit"] = limit
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    sql = f"""
        SELECT t.value AS value, COUNT(*) AS count
        FROM jobs j, json_each(j.{field}) t{where}
        GROUP BY t.value ORDER BY count DESC, value LIMIT :limit
    """
    return [dict(row) for row in conn.execute(sql, params)]


def timeline(conn: sqlite3.Connection, *, days: int = 30, **filters: Any) -> list[dict[str, Any]]:
    """Volume d'offres par jour de publication."""
    clauses, params = _filters(**filters)
    clauses.append("COALESCE(j.posted_at, j.first_seen_at) IS NOT NULL")
    params["days"] = days
    where = " AND ".join(clauses)
    sql = f"""
        SELECT substr(COALESCE(j.posted_at, j.first_seen_at), 1, 10) AS day,
               COUNT(*) AS count
        FROM jobs j WHERE {where}
        GROUP BY day ORDER BY day DESC LIMIT :days
    """
    return list(reversed([dict(r) for r in conn.execute(sql, params)]))


def get(conn: sqlite3.Connection, fingerprint: str) -> dict[str, Any] | None:
    """Une offre complete par son empreinte."""
    row = conn.execute("SELECT * FROM jobs WHERE fingerprint = ?", (fingerprint,)).fetchone()
    return row_to_dict(row) if row else None


def summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Vue d'ensemble du corpus : volumes, couverture, fraicheur."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT source) AS sources,
               COUNT(DISTINCT company) AS companies,
               MIN(COALESCE(posted_at, first_seen_at)) AS oldest,
               MAX(COALESCE(posted_at, first_seen_at)) AS newest,
               SUM(CASE WHEN lat IS NOT NULL THEN 1 ELSE 0 END) AS geolocated
        FROM jobs
        """
    ).fetchone()
    return {
        **dict(row),
        "by_source": facets(conn, "source", limit=50),
        "by_country": facets(conn, "country", limit=20),
    }
