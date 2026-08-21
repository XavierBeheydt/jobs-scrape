"""Reglages Scrapy du projet.

Deux partis pris structurent ce fichier.

**La deontologie n'est pas configurable.** ``ROBOTSTXT_OBEY`` reste a ``True``,
la concurrence est basse et l'User-Agent identifie le projet avec une adresse de
contact. Un operateur qui voit nos requetes dans ses logs doit pouvoir savoir
qui frappe et nous joindre.

**Le chargement des spiders est dynamique.** Les collecteurs vivent dans des
paquets distincts, installes separement ; ``SPIDER_MODULES`` ne les verrait
jamais. On branche donc un chargeur maison sur le registre d'entry points.
"""

from __future__ import annotations

import os

BOT_NAME = "jobs-scrape"

# Les spiders viennent des modules installes, pas d'un paquet fige.
SPIDER_LOADER_CLASS = "jobs_scrape.spiderloader.RegistrySpiderLoader"
SPIDER_MODULES: list[str] = []
NEWSPIDER_MODULE = ""

# -- Conduite ------------------------------------------------------------
ROBOTSTXT_OBEY = True

USER_AGENT = os.environ.get(
    "JOBS_SCRAPE_USER_AGENT",
    "jobs-scrape/0.1 (+https://github.com/XavierBeheydt/jobs-scrape)",
)

CONCURRENT_REQUESTS = 8
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 1.0
DOWNLOAD_TIMEOUT = 30

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1.0
AUTOTHROTTLE_MAX_DELAY = 30.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

RETRY_ENABLED = True
RETRY_TIMES = 3
# 403 est volontairement absent : un refus d'acces se respecte, il ne se retente pas.
RETRY_HTTP_CODES = [408, 429, 500, 502, 503, 504, 522, 524]

# -- Cache de developpement ---------------------------------------------
# Active a la demande. Pendant la mise au point d'un parseur on relance la meme
# requete des dizaines de fois : la servir depuis le disque evite de matraquer
# un serveur pour rien.
HTTPCACHE_ENABLED = os.environ.get("JOBS_SCRAPE_CACHE", "").lower() in {"1", "true", "yes"}
HTTPCACHE_EXPIRATION_SECS = 86400
HTTPCACHE_DIR = "httpcache"
HTTPCACHE_IGNORE_HTTP_CODES = [403, 404, 429, 500, 502, 503]

# -- Pipelines -----------------------------------------------------------
# L'ordre compte : on normalise, on valide, puis on ecarte les doublons AVANT
# d'enrichir. Enrichir un doublon serait du travail perdu -- et potentiellement
# un appel de modele facture pour rien.
ITEM_PIPELINES = {
    "jobs_scrape.pipelines.normalize.NormalizePipeline": 100,
    "jobs_scrape.pipelines.validate.ValidatePipeline": 200,
    "jobs_scrape.pipelines.dedupe.DedupePipeline": 300,
    "jobs_scrape.pipelines.enrich.EnrichPipeline": 400,
    "jobs_scrape.pipelines.export.ExportPipeline": 900,
}

# -- Sorties -------------------------------------------------------------
DATA_DIR = os.environ.get("JOBS_SCRAPE_DATA_DIR", "data")
SQLITE_PATH = os.environ.get("JOBS_SCRAPE_DB", os.path.join(DATA_DIR, "jobs.db"))
JSONL_ENABLED = True

# -- Divers --------------------------------------------------------------
LOG_LEVEL = os.environ.get("JOBS_SCRAPE_LOG_LEVEL", "INFO")
TELNETCONSOLE_ENABLED = False
REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"
