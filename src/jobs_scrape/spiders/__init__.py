"""Classes de base dont heritent les modules de collecte.

Trois socles, un par mode d'acces :

``BaseJobSpider``     tronc commun (identite de la source, limite, horodatage)
``ApiJobSpider``      interrogation d'une interface JSON paginee
``HtmlJobSpider``     liste paginee puis pages de detail, avec aide JSON-LD
``SitemapJobSpider``  parcours guide par un sitemap XML

Ecrire un collecteur revient a heriter du socle adapte et a remplir deux ou
trois methodes.
"""

from jobs_scrape.spiders.api import ApiJobSpider
from jobs_scrape.spiders.base import BaseJobSpider
from jobs_scrape.spiders.html import HtmlJobSpider
from jobs_scrape.spiders.sitemap import SitemapJobSpider

__all__ = ["BaseJobSpider", "ApiJobSpider", "HtmlJobSpider", "SitemapJobSpider"]
