"""Stockage : upsert, index plein-texte, conservation de la premiere vue."""

from conftest import make_job

from jobs_scrape import storage


def test_upsert_signale_la_nouveaute(db):
    job = make_job()
    assert storage.upsert(db, job) is True
    assert storage.upsert(db, job) is False
    assert storage.total(db) == 1


def test_first_seen_at_ne_recule_jamais(db):
    """C'est ce qui permet de mesurer la duree de publication d'une annonce."""
    job = make_job()
    storage.upsert(db, job, seen_at="2026-01-01T00:00:00Z")
    storage.upsert(db, job, seen_at="2026-06-01T00:00:00Z")
    row = db.execute("SELECT first_seen_at, last_seen_at FROM jobs").fetchone()
    assert row["first_seen_at"].startswith("2026-01-01")
    assert row["last_seen_at"].startswith("2026-06-01")


def test_upsert_rafraichit_le_contenu(db):
    storage.upsert(db, make_job(title="Ancien intitulé"))
    storage.upsert(db, make_job(title="Nouvel intitulé"))
    assert storage.total(db) == 1
    assert db.execute("SELECT title FROM jobs").fetchone()["title"] == "Nouvel intitulé"


def test_listes_serialisees_puis_relues(db):
    storage.upsert(db, make_job(skills=["python", "go"]))
    row = storage.row_to_dict(db.execute("SELECT * FROM jobs").fetchone())
    assert row["skills"] == ["python", "go"]


def test_index_fts_suit_les_suppressions(db):
    """L'index est tenu par declencheurs : une suppression doit s'y refleter."""
    storage.upsert(db, make_job())
    db.commit()
    assert db.execute("SELECT COUNT(*) c FROM jobs_fts WHERE jobs_fts MATCH 'python'").fetchone()["c"] == 1
    db.execute("DELETE FROM jobs")
    db.commit()
    assert db.execute("SELECT COUNT(*) c FROM jobs_fts WHERE jobs_fts MATCH 'python'").fetchone()["c"] == 0


def test_counts_by_source(db):
    storage.upsert(db, make_job(source="a", external_id="1", url="https://a/1"))
    storage.upsert(db, make_job(source="a", external_id="2", url="https://a/2"))
    storage.upsert(db, make_job(source="b", external_id="3", url="https://b/3"))
    assert storage.counts_by_source(db) == [("a", 2), ("b", 1)]
