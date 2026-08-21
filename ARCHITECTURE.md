# Architecture

## Vue d'ensemble

```
   COLLECTE                ENRICHISSEMENT        STOCKAGE           EXPLORATION
 +------------+          +--------------+     +-----------+     +--------------+
 |  modules   |--JobItem-|   greffons   |---->|  JSONL    |<----|  serveur MCP |--> IA
 | (API/HTML) |          | (mots-cles)  |     |  + SQLite |     +--------------+
 +------------+          +--------------+     |  + FTS5   |<----|  interface   |--> humain
                                              +-----------+     +--------------+
```

Le depot present ne contient que le coeur. Les collecteurs, les enrichisseurs,
le serveur MCP et l'interface vivent dans des depots separes et se branchent
dessus.

## Pourquoi des modules separes

Trois raisons, dans cet ordre d'importance.

**Isoler les risques.** Les sites n'ont pas tous les memes conditions
d'utilisation. Un collecteur dont les CGU sont restrictives vit dans un depot
prive ; le reste du projet reste public sans avoir a arbitrer entre les deux.

**Isoler les dependances.** L'extraction statistique de mots-cles tire `yake`,
l'interface tire `fastapi` -- rien de tout cela n'a a etre installe pour lancer
une simple collecte.

**Isoler les pannes.** Un site refond son balisage, son module casse. Les dix
autres continuent, et le correctif se publie sans toucher au coeur.

## Le contrat

Un module se declare par un *entry point* :

```toml
[project.entry-points."jobs_scrape.sources"]
jobroom = "jobs_scrape_mod_jobroom:SOURCE"
```

`SOURCE` est un `SourceMeta` : il porte la classe du spider, mais aussi le mode
d'acces, la zone couverte, les variables d'environnement necessaires et les
reserves connues. Cette information etant declarative, `jobs-scrape list`
renseigne l'utilisateur **sans executer le moindre spider**.

Le coeur n'importe aucun module en dur. Installer un paquet suffit a le rendre
visible ; le desinstaller suffit a le retirer.

### Integration avec Scrapy

Scrapy decouvre ses spiders en parcourant `SPIDER_MODULES`, ce qui suppose
qu'ils vivent dans l'arborescence du projet. Ce n'est pas le cas ici. Scrapy
prevoit la substitution : `SPIDER_LOADER_CLASS` pointe vers
`RegistrySpiderLoader`, qui interroge le registre. Pour le reste du framework --
`scrapy crawl`, les statistiques, les extensions -- un spider de module est
indiscernable d'un spider natif.

## Les trois socles de collecte

| Socle | Pour quoi | Ce que le module ecrit |
|---|---|---|
| `ApiJobSpider` | interface JSON paginee | `extract_rows()`, `parse_row()` |
| `HtmlJobSpider` | liste paginee puis fiches | `build_listing_urls()`, `extra_fields()` |
| `SitemapJobSpider` | sitemap XML | `sitemap_rules`, `extra_fields()` |

Un site qui publie du JSON-LD `JobPosting` ne demande **aucun code d'extraction** :
`jobs_scrape.jsonld` s'en charge.

### Scrapy sait interroger des API

C'est l'un des partis pris du projet. Scrapy est un moteur HTTP asynchrone ; le
HTML n'est qu'un contenu parmi d'autres. Appeler une API depuis Scrapy plutot
qu'avec une boucle `requests` apporte gratuitement la limitation de debit
adaptative, les reessais, le cache disque, les statistiques, et surtout **la meme
chaine de pipelines** que les collecteurs HTML -- donc le meme schema en sortie.

```python
from scrapy.http import JsonRequest

yield JsonRequest(url=..., data={"onlineSince": 30}, callback=self.parse)
# puis, dans le callback : response.json()
```

## La chaine de traitement

| Rang | Pipeline | Role |
|---|---|---|
| 100 | `NormalizePipeline` | dates en ISO, pays en code, taux bornes, empreinte |
| 200 | `ValidatePipeline` | exige source, URL et intitule ; rien de plus |
| 300 | `DedupePipeline` | ecarte les doublons de la collecte en cours |
| 400 | `EnrichPipeline` | applique les greffons installes |
| 900 | `ExportPipeline` | ecrit en JSONL et en SQLite |

L'ordre est raisonne : **dedupliquer avant d'enrichir**. Enrichir un doublon est
un travail perdu -- et, avec le greffon fonde sur un modele de langage, un appel
facture pour rien.

Le seuil de validation est volontairement bas. Une annonce sans salaire ni
localisation reste utile ; sans intitule ni lien, elle ne l'est pas.

## Stockage

**JSONL** : une archive par collecte, horodatee, jamais modifiee. Elle conserve
ce que la source a repondu ce jour-la, ce qui permet de rejouer un traitement
apres correction d'un parseur sans retourner solliciter le site.

**SQLite** : l'etat courant, une ligne par offre, mise a jour par `UPSERT` sur
l'empreinte. `first_seen_at` n'est jamais rejoue en arriere -- c'est ce qui
permet de mesurer la duree de publication reelle d'une annonce.

L'empreinte est `sha1(source | external_id)`, avec repli sur l'URL. Preferer
l'identifiant a l'URL rend la deduplication insensible aux parametres de suivi
et aux changements de slug.

**FTS5**, inclus dans le `sqlite3` de la bibliotheque standard, fournit la
recherche plein-texte classee par BM25 sans aucune dependance supplementaire.
L'index est tenu par declencheurs SQL : une ecriture directe en base ne peut pas
le desynchroniser. Le tokeniseur utilise `remove_diacritics 2`, sans quoi
« developpeur » ne trouverait pas « developpeur » accentue.

La ville fait partie des colonnes indexees : on cherche un emploi par « quoi
**et** ou », et l'utilisateur tape les deux dans le meme champ.

## Ajouter une source

1. Nouveau depot, dependance vers `jobs-scrape`.
2. Un `spider.py` heritant du socle adapte.
3. Un `SOURCE = SourceMeta(...)` dans `__init__.py`, expose en entry point.
4. Une reponse reelle figee dans `tests/fixtures/`, rejouee par
   `jobs_scrape.testing` -- **les tests ne touchent jamais le reseau**.
5. Une ligne dans `config/modules.yml`.

Aucun fichier du coeur n'est a modifier.
