# jobs-scrape

Collecte, enrichissement et exploration d'offres d'emploi **suisses et francaises**.

```
   COLLECTE                ENRICHISSEMENT        STOCKAGE          EXPLORATION
 +------------+          +--------------+     +-----------+     +--------------+
 | 7 modules  |--JobItem-| mots-cles    |---->|  JSONL    |<----| serveur MCP  |--> IA
 | (API/HTML) |          | fr/de/it/en  |     |  + SQLite |     +--------------+
 +------------+          +--------------+     |  + FTS5   |<----| interface web|--> humain
                                              +-----------+     +--------------+
```

Ce depot est le **coeur** : schema normalise, socles de spiders, chaine de
traitement, recherche plein-texte et chargeur de modules. Les collecteurs,
l'enrichisseur, le serveur MCP et l'interface vivent dans des depots separes.

## Installation

```bash
git clone git@github.com:XavierBeheydt/jobs-scrape.git
cd jobs-scrape
uv sync
uv run jobs-scrape list        # fonctionne sans aucun module installe

uv run jobs-scrape modules sync   # installe les modules declares
uv run jobs-scrape list           # 8 collecteurs + 1 enrichisseur
```

Les depots prives passent par `git+ssh` : l'authentification SSH de `gh` deja
presente sur la machine suffit, aucun jeton a stocker.

## Prise en main

```bash
uv run jobs-scrape crawl jobroom --limit 200         # API du service public suisse
uv run jobs-scrape crawl apec -a keywords="data engineer"
uv run jobs-scrape crawl-all --limit 100             # tous les collecteurs actifs

uv run jobs-scrape search "python kubernetes" --region GE
uv run jobs-scrape search --skill soins_infirmiers --workload-min 80
uv run jobs-scrape terms --field skills --top 30
uv run jobs-scrape stats

uv run jobs-scrape-ui                                # http://127.0.0.1:8000
claude mcp add jobs-scrape -- uv run jobs-scrape-mcp
```

## Les onze depots

| Depot | Visibilite | Role |
|---|---|---|
| [`jobs-scrape`](https://github.com/XavierBeheydt/jobs-scrape) | public | **ce depot** — schema, spiders de base, pipelines, recherche, CLI |
| [`…-mod-jobroom`](https://github.com/XavierBeheydt/jobs-scrape-mod-jobroom) | public | Service public suisse (SECO) — API sans auth, ~69 000 annonces |
| [`…-mod-apec`](https://github.com/XavierBeheydt/jobs-scrape-mod-apec) | public | Offres cadres France — API sans auth |
| [`…-mod-approachpeople`](https://github.com/XavierBeheydt/jobs-scrape-mod-approachpeople) | public | Cabinet de recrutement — sitemap, trilingue |
| [`…-mod-agencies-ge`](https://github.com/XavierBeheydt/jobs-scrape-mod-agencies-ge) | public | 126 agences ge.ch — un parseur schema.org pour 19 sites |
| [`…-mod-adzuna`](https://github.com/XavierBeheydt/jobs-scrape-mod-adzuna) | public | Agregateur FR/CH — cle simple, pas d'OAuth |
| [`…-mod-jobup`](https://github.com/XavierBeheydt/jobs-scrape-mod-jobup) | **prive** | Suisse romande — CGU restrictives |
| [`…-mod-indeed`](https://github.com/XavierBeheydt/jobs-scrape-mod-indeed) | **prive** | Non fonctionnel — 403 pare-feu, livre pour memoire |
| [`…-mod-keywords`](https://github.com/XavierBeheydt/jobs-scrape-mod-keywords) | public | Extraction de competences, 211 entrees fr/de/it/en |
| [`…-mcp`](https://github.com/XavierBeheydt/jobs-scrape-mcp) | public | Serveur MCP — le corpus interrogeable par une IA |
| [`…-ui`](https://github.com/XavierBeheydt/jobs-scrape-ui) | public | Interface web — recherche a facettes et tableau de bord |

## Sources : ce qui marche, et pourquoi

Chaque mode d'acces a ete verifie par requete reelle. Le detail — mesures,
`robots.txt`, volumetries — est dans [SOURCES.md](SOURCES.md).

| Module | Acces | Zone | Note |
|---|---|---|---|
| `jobroom` | API JSON sans auth | CH | ~69 000 annonces geolocalisees, donnees officielles |
| `apec` | API JSON sans auth | FR | `robots.txt` sans aucune regle `Disallow` |
| `jobup` | HTML + JSON-LD | CH | `/api/` ferme par robots ; le HTML est autorise |
| `approachpeople` | Sitemap → HTML | CH/FR/EU | ~1 100 offres, fr / de / en |
| `agencies-ge` | JSON-LD generique | CH-GE | 19 agences sur 126 exposent un balisage exploitable |
| `adzuna` | API a cle simple | FR/CH | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` |
| `indeed` | — | — | **Bloque** : 403 pare-feu applicatif |

Ecartes en connaissance de cause : **France Travail** (OAuth obligatoire, exclu
par principe) et **HelloWork** (CGU interdisant explicitement la reutilisation).

## Oui, Scrapy sait interroger des API

Trois des collecteurs sont des clients d'interfaces JSON et tournent
entierement dans Scrapy. Le HTML n'est qu'un contenu parmi d'autres pour un
moteur HTTP asynchrone :

```python
from scrapy.http import JsonRequest

class MonSpider(ApiJobSpider):
    endpoint = "https://exemple.test/api/offres"

    def payload(self, page):
        return {"onlineSince": 30}

    def extract_rows(self, response):
        return response.json()["resultats"]
```

On garde limitation de debit adaptative, reessais, cache disque, statistiques —
et la meme chaine de pipelines que les collecteurs HTML, donc le meme schema en
sortie.

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

Aucun fichier du coeur n'est a modifier. Details dans
[ARCHITECTURE.md](ARCHITECTURE.md).

## Conduite

Cables dans `settings.py`, non negociables :

- `ROBOTSTXT_OBEY = True`, sans exception ni derogation par module ;
- limitation de debit adaptative, concurrence cible d'**une** requete, deux
  connexions simultanees par domaine, une seconde de delai ;
- User-Agent identifiable, portant l'URL du projet ;
- `403` absent des codes reessayes : un refus d'acces se respecte.

Seules des **offres publiques** sont collectees. Aucune donnee de candidat,
aucun contournement d'authentification, aucune tentative de franchir un
pare-feu applicatif. Les sources dont les CGU interdisent la reutilisation sont
ecartees et documentees comme telles ; celles dont les CGU sont restrictives
vivent dans des depots prives.

Un depot prive limite la diffusion du code ; il ne change rien au statut
juridique de la collecte. Verifiez les conditions d'utilisation des sites que
vous ciblez.

## Developpement

```bash
uv sync --extra dev
uv run pytest -q          # hors ligne : aucune requete vers les sites collectes
uv run ruff check src tests
JOBS_SCRAPE_CACHE=1 uv run jobs-scrape crawl <source>   # cache disque en mise au point
```

| Variable | Effet |
|---|---|
| `JOBS_SCRAPE_DATA_DIR` | repertoire de sortie (defaut `data`) |
| `JOBS_SCRAPE_DB` | chemin de la base SQLite |
| `JOBS_SCRAPE_CACHE` | `1` pour activer le cache HTTP disque |
| `JOBS_SCRAPE_USER_AGENT` | remplacer l'User-Agent |
| `JOBS_SCRAPE_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
