"""Persistance SQLite des offres, avec index plein-texte.

Le choix de SQLite n'est pas un pis-aller. Le volume vise -- quelques centaines
de milliers d'annonces -- tient largement, il n'y a aucun service a maintenir, et
surtout **FTS5 est inclus dans le module ``sqlite3`` de la bibliotheque standard** :
on obtient une recherche plein-texte classee par BM25 sans ajouter une seule
dependance.

L'index est tenu a jour par declencheurs plutot que depuis Python. Une ecriture
directe en base -- un script d'appoint, une correction a la main -- ne peut donc
pas desynchroniser l'index.

Le tokeniseur est configure avec ``remove_diacritics 2`` : sans lui, chercher
« developpeur » ne trouverait pas « developpeur » ecrit avec ses accents, ce qui
serait redhibitoire sur un corpus francophone.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from jobs_scrape.items import FIELD_NAMES, LIST_FIELDS, JobItem
from jobs_scrape.loaders import utc_now_iso

# Colonnes de la table, dans l'ordre. ``fingerprint`` sert de cle primaire ;
# les deux horodatages sont geres par la couche de stockage, pas par les spiders.
COLUMNS: tuple[str, ...] = tuple(
    name for name in FIELD_NAMES if name != "scraped_at"
) + ("first_seen_at", "last_seen_at")

# Colonnes versees a l'index plein-texte. ``city`` en fait partie a dessein :
# on cherche un emploi par « quoi ET ou », et l'utilisateur tape les deux dans
# le meme champ. L'exclure obligerait a passer la ville en filtre explicite.
_TEXT_COLUMNS = ("title", "company", "city", "description", "keywords", "skills")

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS jobs (
    fingerprint    TEXT PRIMARY KEY,
    source         TEXT NOT NULL,
    external_id    TEXT,
    url            TEXT NOT NULL,
    title          TEXT NOT NULL,
    company        TEXT,
    description    TEXT,
    location_raw   TEXT,
    city           TEXT,
    postal_code    TEXT,
    region         TEXT,
    country        TEXT,
    lat            REAL,
    lon            REAL,
    contract_type  TEXT,
    workload_min   INTEGER,
    workload_max   INTEGER,
    salary_min     REAL,
    salary_max     REAL,
    salary_currency TEXT,
    posted_at      TEXT,
    expires_at     TEXT,
    lang           TEXT,
    keywords       TEXT,
    skills         TEXT,
    seniority      TEXT,
    remote_policy  TEXT,
    languages      TEXT,
    occupations    TEXT,
    apply_url      TEXT,
    first_seen_at  TEXT NOT NULL,
    last_seen_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_source    ON jobs(source);
CREATE INDEX IF NOT EXISTS idx_jobs_region    ON jobs(region);
CREATE INDEX IF NOT EXISTS idx_jobs_city      ON jobs(city);
CREATE INDEX IF NOT EXISTS idx_jobs_company   ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at ON jobs(posted_at);
CREATE INDEX IF NOT EXISTS idx_jobs_last_seen ON jobs(last_seen_at);

CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(
    {", ".join(_TEXT_COLUMNS)},
    content='jobs',
    content_rowid='rowid',
    tokenize="unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS jobs_fts_insert AFTER INSERT ON jobs BEGIN
    INSERT INTO jobs_fts(rowid, {", ".join(_TEXT_COLUMNS)})
    VALUES (new.rowid, {", ".join("new." + c for c in _TEXT_COLUMNS)});
END;

CREATE TRIGGER IF NOT EXISTS jobs_fts_delete AFTER DELETE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, {", ".join(_TEXT_COLUMNS)})
    VALUES ('delete', old.rowid, {", ".join("old." + c for c in _TEXT_COLUMNS)});
END;

CREATE TRIGGER IF NOT EXISTS jobs_fts_update AFTER UPDATE ON jobs BEGIN
    INSERT INTO jobs_fts(jobs_fts, rowid, {", ".join(_TEXT_COLUMNS)})
    VALUES ('delete', old.rowid, {", ".join("old." + c for c in _TEXT_COLUMNS)});
    INSERT INTO jobs_fts(rowid, {", ".join(_TEXT_COLUMNS)})
    VALUES (new.rowid, {", ".join("new." + c for c in _TEXT_COLUMNS)});
END;
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Ouvre la base et garantit que le schema est en place."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    # WAL : lectures concurrentes possibles pendant qu'une collecte ecrit, ce qui
    # permet de consulter l'interface ou le serveur MCP sans attendre la fin du run.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def item_to_row(item: JobItem, seen_at: str | None = None) -> dict[str, Any]:
    """Convertit une offre en ligne prete pour SQLite.

    Les champs de type liste sont serialises en JSON : c'est lisible depuis
    n'importe quel client SQL et indexable par FTS5 sans traitement particulier.
    """
    seen_at = seen_at or utc_now_iso()
    row: dict[str, Any] = {}
    for column in COLUMNS:
        if column in ("first_seen_at", "last_seen_at"):
            row[column] = seen_at
            continue
        value = getattr(item, column, None)
        if column in LIST_FIELDS:
            value = json.dumps(value or [], ensure_ascii=False)
        row[column] = value
    return row


_UPSERT = f"""
INSERT INTO jobs ({", ".join(COLUMNS)})
VALUES ({", ".join(":" + c for c in COLUMNS)})
ON CONFLICT(fingerprint) DO UPDATE SET
    {", ".join(f"{c} = excluded.{c}" for c in COLUMNS
               if c not in ("fingerprint", "first_seen_at"))}
"""
# ``first_seen_at`` est volontairement exclu de la mise a jour : c'est la date de
# premiere apparition de l'offre, et elle ne doit jamais reculer. C'est ce qui
# permet ensuite de mesurer la duree de publication reelle d'une annonce.


def upsert(conn: sqlite3.Connection, item: JobItem, seen_at: str | None = None) -> bool:
    """Insere ou rafraichit une offre. Renvoie ``True`` si elle etait nouvelle."""
    row = item_to_row(item, seen_at)
    existed = conn.execute(
        "SELECT 1 FROM jobs WHERE fingerprint = ?", (row["fingerprint"],)
    ).fetchone() is not None
    conn.execute(_UPSERT, row)
    return not existed


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Ligne SQLite en dictionnaire, listes JSON deserialisees."""
    data = dict(row)
    for field in LIST_FIELDS:
        if field in data and isinstance(data[field], str):
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                data[field] = []
    return data


def counts_by_source(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    return [
        (r["source"], r["n"])
        for r in conn.execute(
            "SELECT source, COUNT(*) AS n FROM jobs GROUP BY source ORDER BY n DESC"
        )
    ]


def total(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
