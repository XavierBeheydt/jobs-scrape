# jobs-scrape

Collecte, enrichissement et exploration d'offres d'emploi **suisses et francaises**.

Ce depot est le **coeur** : schema normalise, socles de spiders, chaine de traitement,
recherche plein-texte et chargeur de modules. Les collecteurs vivent dans des depots
separes et se branchent par *entry points*.

```
   COLLECTE              ENRICHISSEMENT      STOCKAGE          EXPLORATION
 +------------+        +--------------+   +-----------+   +--------------+
 |  modules   |-JobItem-|  greffons   |-->|  JSONL    |<--|  serveur MCP |--> IA
 | (API/HTML) |        | (mots-cles)  |   |  + SQLite |   +--------------+
 +------------+        +--------------+   |  + FTS5   |<--|  interface   |--> humain
                                          +-----------+   +--------------+
```

## Installation

```bash
git clone git@github.com:XavierBeheydt/jobs-scrape.git
cd jobs-scrape
uv sync
uv run jobs-scrape list      # fonctionne sans aucun module installe
```

Puis on installe les collecteurs voulus, declares dans `config/modules.yml` :

```bash
uv run jobs-scrape modules list      # etat declare / installe
uv run jobs-scrape modules sync      # installe les modules actives
```

Les depots prives passent par `git+ssh` : l'authentification SSH de `gh` deja
presente sur la machine suffit, aucun jeton a stocker.

## Prise en main

```bash
uv run jobs-scrape crawl jobroom --limit 50        # une API JSON
uv run jobs-scrape crawl jobup --limit 20 -a term=developpeur
uv run jobs-scrape crawl-all --limit 100           # tous les collecteurs actifs

uv run jobs-scrape search "python kubernetes" --region GE
uv run jobs-scrape search --skill python --skill docker --workload-min 80
uv run jobs-scrape terms --field skills --top 30
uv run jobs-scrape stats
```

Les donnees atterrissent dans `data/` : une archive JSONL par collecte, et
`data/jobs.db` pour l'etat courant. Rien de tout cela n'est versionne.

## Sources

Chaque mode d'acces a ete verifie par requete reelle ; le detail, mesures et
`robots.txt` a l'appui, est dans [SOURCES.md](SOURCES.md).

| Module | Acces | Zone | Note |
|---|---|---|---|
| `jobroom` | API JSON sans auth | CH | Service public (SECO). ~69 000 annonces, geolocalisees |
| `apec` | API JSON sans auth | FR | Offres cadres |
| `jobup` | HTML + JSON-LD | CH | Depot prive : CGU restrictives |
| `approachpeople` | Sitemap -> HTML | CH/FR/IE | ~1 100 offres |
| `agencies-ge` | JSON-LD generique | CH-GE | 125 agences listees par ge.ch |
| `adzuna` | API a cle simple | FR/CH | Necessite `ADZUNA_APP_ID` et `ADZUNA_APP_KEY` |
| `indeed` | HTML | CH/FR | **Desactive** : bloque par pare-feu applicatif (403) |

Ecartes en connaissance de cause : **France Travail** (OAuth obligatoire, exclu
par principe du projet) et **HelloWork** (CGU interdisant explicitement la
reutilisation).

## Oui, Scrapy sait interroger des API

C'est l'un des partis pris du projet, et la question meritait d'etre tranchee.
Scrapy est un moteur HTTP asynchrone ; le HTML n'est qu'un contenu parmi
d'autres. Passer par Scrapy plutot que par une boucle `requests` apporte
gratuitement la limitation de debit adaptative, les reessais avec backoff, le
cache disque, les statistiques -- et surtout **la meme chaine de pipelines** que
les collecteurs HTML, donc le meme schema en sortie.

```python
from scrapy.http import JsonRequest

class MonSpider(ApiJobSpider):
    endpoint = "https://exemple.test/api/offres"

    def payload(self, page):
        return {"onlineSince": 30}

    def extract_rows(self, response):
        return response.json()["resultats"]
```

Deux des sources les plus fiables du projet fonctionnent ainsi.

## Ajouter une source

1. Nouveau depot, dependance vers `jobs-scrape`.
2. Un spider heritant d'`ApiJobSpider`, `HtmlJobSpider` ou `SitemapJobSpider`.
3. Un `SOURCE = SourceMeta(...)` expose en entry point :

```toml
[project.entry-points."jobs_scrape.sources"]
masource = "jobs_scrape_mod_masource:SOURCE"
```

4. Des tests **hors ligne**, sur une reponse reelle figee, via `jobs_scrape.testing`.
5. Une ligne dans `config/modules.yml`.

Aucun fichier du coeur n'est a modifier. Les details sont dans
[ARCHITECTURE.md](ARCHITECTURE.md).

## Conduite

Ces reglages ne sont pas negociables et sont cables dans `settings.py` :

- `ROBOTSTXT_OBEY = True`, sans exception ni derogation par module ;
- limitation de debit adaptative, concurrence cible d'**une** requete, 2 connexions
  simultanees par domaine, 1 seconde de delai ;
- User-Agent identifiable, portant l'URL du projet ;
- `403` absent de la liste des codes reessayes : un refus d'acces se respecte.

Seules des **offres publiques** sont collectees. Aucune donnee de candidat,
aucun contournement d'authentification, aucune tentative de passer un pare-feu
applicatif. Les sources dont les conditions d'utilisation interdisent la
reutilisation sont ecartees et documentees comme telles.

Un depot prive limite la diffusion d'un collecteur ; il ne change rien au statut
juridique de la collecte. Verifiez les conditions d'utilisation des sites que
vous ciblez.

## Developpement

```bash
uv sync --extra dev
uv run pytest -q          # hors ligne : aucune requete vers les sites collectes
uv run ruff check src tests
JOBS_SCRAPE_CACHE=1 uv run jobs-scrape crawl <source>   # cache disque pour la mise au point
```

| Variable | Effet |
|---|---|
| `JOBS_SCRAPE_DATA_DIR` | repertoire de sortie (defaut `data`) |
| `JOBS_SCRAPE_DB` | chemin de la base SQLite |
| `JOBS_SCRAPE_CACHE` | `1` pour activer le cache HTTP disque |
| `JOBS_SCRAPE_USER_AGENT` | remplacer l'User-Agent |
| `JOBS_SCRAPE_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
