"""Ecriture des offres : archive JSONL et base SQLite."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from jobs_scrape import storage
from jobs_scrape.loaders import utc_now_iso

logger = logging.getLogger(__name__)


class ExportPipeline:
    """Ecrit chaque offre aux deux formats, qui ne servent pas a la meme chose.

    Le **JSONL** est une archive : un fichier par collecte, horodate, jamais
    modifie. Il conserve exactement ce que la source a repondu ce jour-la, ce qui
    permet de rejouer un traitement apres correction d'un parseur sans retourner
    solliciter le site.

    La **base SQLite** est l'etat courant : une ligne par offre, mise a jour a
    chaque nouvelle apparition. C'est elle qu'interrogent la recherche,
    l'interface et le serveur MCP.
    """

    def __init__(self, data_dir: str = "data", db_path: str | None = None, jsonl: bool = True):
        self.data_dir = Path(data_dir)
        self.db_path = db_path or str(self.data_dir / "jobs.db")
        self.jsonl_enabled = jsonl
        self.conn = None
        self.file = None
        self.written = 0
        self.new = 0

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        return cls(
            data_dir=settings.get("DATA_DIR", "data"),
            db_path=settings.get("SQLITE_PATH"),
            jsonl=settings.getbool("JSONL_ENABLED", True),
        )

    def open_spider(self, spider):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.conn = storage.connect(self.db_path)
        self.run_seen_at = utc_now_iso()

        if self.jsonl_enabled:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            path = self.data_dir / f"{spider.name}_{stamp}.jsonl"
            self.file = path.open("w", encoding="utf-8")
            logger.info("archive de la collecte : %s", path)

    def process_item(self, item, spider):
        if self.file is not None:
            self.file.write(json.dumps(asdict(item), ensure_ascii=False) + "\n")

        if storage.upsert(self.conn, item, seen_at=self.run_seen_at):
            self.new += 1
            spider.crawler.stats.inc_value("jobs/new")
        else:
            spider.crawler.stats.inc_value("jobs/updated")

        self.written += 1
        # Un commit periodique plutot qu'un seul a la fin : une collecte
        # interrompue -- coupure reseau, Ctrl-C -- conserve ce qui a ete lu.
        if self.written % 100 == 0:
            self.conn.commit()
        return item

    def close_spider(self, spider):
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
        if self.file is not None:
            self.file.close()
        logger.info(
            "%s offre(s) ecrite(s), dont %s nouvelle(s) ; base : %s",
            self.written, self.new, self.db_path,
        )
