# Etude de faisabilite des sources

Sondages HTTP reels effectues le **2026-08-21**. Chaque ligne a ete verifiee par requete,
robots.txt lu. Ce document justifie le mode d'acces retenu pour chaque module.

## Sources retenues

### Job-Room / SECO — service public de l'emploi suisse

- **Mode** : API REST JSON, **sans authentification**
- **Endpoint** : `POST https://www.job-room.ch/jobadservice/api/jobAdvertisements/_search?page=&size=`
- **Mesure** : `200 OK`, **69 458 annonces** disponibles
- **Pagination** : en-tete `x-total-count` + en-tetes `Link` (`next` / `last` / `first`)
- **robots.txt** : `/job-search/` (l'interface web) est interdit ; le chemin `/jobadservice/api/` ne l'est pas
- **Qualite** : la meilleure du lot. Coordonnees lat/lon, canton, NPA, code communal,
  entreprise complete, taux d'activite min/max, langues exigees, codes metier,
  descriptions multilingues (`languageIsoCode` en `de`/`fr`/`it`/`en`)

C'est une source publique officielle : aucune ambiguite d'usage.

### APEC — offres cadres, France

- **Mode** : API REST JSON, **sans authentification**
- **Endpoint** : `POST https://www.apec.fr/cms/webservices/rechercheOffre`
- **Mesure** : `200 OK`
- **Pagination** : champ `pagination.range` / `pagination.startIndex` dans le corps
- **robots.txt** : `User-agent: *` sans **aucune** regle `Disallow` — tout est autorise

### jobup.ch — Suisse romande

- **Mode** : HTML + JSON-LD
- **Chemins** : liste `/fr/emplois/?term=` -> detail `/fr/emplois/detail/<uuid>/`
- **Mesure** : `200 OK`, `JobPosting` schema.org complet sur les pages de detail
  (`title`, `description`, `hiringOrganization`, `jobLocation` avec rue et NPA,
  `baseSalary` en CHF, `datePosted`)
- **robots.txt** : `/api/` et `/api_proxy/` sont **interdits**. On ne touche donc pas
  a leur API interne et on passe par le HTML, qui est autorise.

### ApproachPeople

- **Mode** : sitemap -> HTML
- **Chemins** : `job-sitemap.xml` + `job-sitemap2.xml` -> `/job/<slug>` et `/fr/job/<slug>`
- **Mesure** : **1 129 offres** referencees
- **Parsing** : pas de JSON-LD `JobPosting` ; pas de `wp-json/wp/v2/job` (404, le type
  n'est pas expose en REST). WordPress + plugin *JobSearch* : selecteurs CSS sur `<h1>`
  et les blocs `jobsearch-*`
- **robots.txt** : `/job-search*`, `/recherche-emploi*` et `/*?` sont interdits.
  **La voie sitemap est donc la seule conforme** — c'est celle que le module emprunte.

### Agences de placement genevoises (ge.ch)

- **Mode** : spider generique JSON-LD, pilote par `config/agencies.yml`
- **Source de la liste** : <https://www.ge.ch/acceder-milliers-offres-emploi-ligne/agences-placement>
- **Mesure** : **125 domaines** d'agences extraits (adecco.ch, interiman.ch, careerplus.ch,
  coople.com, michaelpage.ch, robertwalters.ch, randstad.ch...)
- Beaucoup de ces sites exposent un `JobPosting` schema.org : un seul spider generique
  les couvre tous. Le robots.txt de chaque domaine est verifie au runtime par Scrapy.

### Adzuna — agregateur FR + CH

- **Mode** : API REST avec cle simple (`app_id` + `app_key`), gratuite, **pas d'OAuth**
- **Mesure** : `400` sans cle, l'endpoint est vivant
- Sert de substitut fonctionnel a Indeed, qui est inatteignable (voir plus bas)

## Sources ecartees, et pourquoi

### Indeed — bloque techniquement

- **Mesure** : `403` sur `https://ch.indeed.com/jobs?q=...` — pare-feu applicatif anti-bot
- Leur `robots.txt` est pourtant permissif : le blocage est au niveau du WAF, pas des regles
- Un module est fourni pour memoire, **desactive par defaut**. Le faire fonctionner
  demanderait un navigateur pilote et des IP residentielles, ce qui sort du cadre du projet.

### France Travail (ex Pole emploi) — OAuth obligatoire

- **Mesure** : `401` sur `api.francetravail.io/partenaire/offresdemploi/v2/offres/search`
- L'API exige un flux OAuth2 `client_credentials`. La consigne du projet exclut OAuth.

### HelloWork — interdit par les CGU

- **Mesure** : `200`, la page repond
- Mais le code source contient cet avertissement : *"En visualisant le code source vous
  acceptez les CGU... Notamment l'article 8.2"*, qui restreint explicitement la reutilisation.
  Son `robots.txt` interdit par ailleurs `/*?`, donc toute recherche parametree.
- **Ecarte pour raison juridique**, pas technique.

### Welcome to the Jungle — reporte

- La recherche s'appuie sur Algolia cote client ; les cles vivent dans le bundle JS et
  changent sans preavis. Le `robots.txt` interdit `/*?`. Candidat de phase 2.

## Regles de conduite appliquees

`ROBOTSTXT_OBEY = True` sans exception · `AUTOTHROTTLE_ENABLED` avec une concurrence
cible de 1 requete · 2 connexions simultanees maximum par domaine · delai de 1 seconde ·
User-Agent identifiable. Seules des **offres publiques** sont collectees : aucune donnee
de candidat, aucun contournement d'authentification.
