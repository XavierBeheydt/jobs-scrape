import sqlite3
import pytest

from jobs_scrape import storage
from jobs_scrape.items import JobItem, compute_fingerprint


@pytest.fixture
def db(tmp_path) -> sqlite3.Connection:
    conn = storage.connect(tmp_path / "jobs.db")
    yield conn
    conn.close()


def make_job(**overrides) -> JobItem:
    values = dict(
        source="testsource", external_id="1", url="https://example.test/1",
        title="Développeur Python senior", company="ACME SA",
        description="Django, PostgreSQL et Kubernetes au quotidien.",
        city="Genève", region="GE", country="CH",
        skills=["python", "django"], keywords=["backend"],
        workload_min=80, workload_max=100, posted_at="2026-08-20", lang="fr",
    )
    values.update(overrides)
    item = JobItem(**values)
    item.fingerprint = compute_fingerprint(item)
    return item


@pytest.fixture
def job():
    return make_job
