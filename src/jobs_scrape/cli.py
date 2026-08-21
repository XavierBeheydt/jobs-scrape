"""Interface en ligne de commande de jobs-scrape."""

from __future__ import annotations

import argparse
import json
import sys

from jobs_scrape import __version__


def _settings():
    """Reglages Scrapy du projet, enrichis des options du manifeste."""
    from scrapy.settings import Settings

    from jobs_scrape import modules

    settings = Settings()
    settings.setmodule("jobs_scrape.settings", priority="project")
    settings.set("ENRICHER_CONFIG", modules.module_config(), priority="project")
    return settings


def _connect(settings=None):
    from jobs_scrape import storage

    settings = settings or _settings()
    return storage.connect(settings.get("SQLITE_PATH", "data/jobs.db"))


def _table(rows: list[list[str]], headers: list[str]) -> str:
    """Rendu tabulaire aligne, sans dependance de mise en forme."""
    columns = list(zip(*([headers] + rows), strict=True)) if rows else [[h] for h in headers]
    widths = [max(len(str(cell)) for cell in column) for column in columns]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True)).rstrip()
    out = [line, "  ".join("-" * w for w in widths).rstrip()]
    for row in rows:
        out.append("  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())
    return "\n".join(out)


# --------------------------------------------------------------- commandes


def cmd_list(args) -> int:
    from jobs_scrape import registry

    sources = registry.sources()
    enrichers = registry.enrichers()

    if args.json:
        print(json.dumps({
            "sources": {
                name: {
                    "access": m.access, "country": m.country, "domains": list(m.domains),
                    "enabled_by_default": m.enabled_by_default, "description": m.description,
                    "notes": m.notes, "missing_env": list(m.missing_env()),
                } for name, m in sources.items()
            },
            "enrichers": {n: {"description": m.description, "order": m.order}
                          for n, m in enrichers.items()},
        }, ensure_ascii=False, indent=2))
        return 0

    if not sources:
        print("Aucun collecteur installe.")
        print("  Declarez-les dans config/modules.yml puis : jobs-scrape modules sync")
    else:
        rows = []
        for name, meta in sources.items():
            state = "actif" if meta.enabled_by_default else "desactive"
            if meta.missing_env():
                state = "manque " + ",".join(meta.missing_env())
            rows.append([name, meta.access, meta.country, state, meta.description[:46]])
        print("COLLECTEURS")
        print(_table(rows, ["nom", "acces", "zone", "etat", "description"]))
        notes = [(n, m.notes) for n, m in sources.items() if m.notes]
        if notes:
            print("\nReserves :")
            for name, note in notes:
                print(f"  {name} : {note}")

    if enrichers:
        print("\nENRICHISSEURS")
        print(_table(
            [[n, str(m.order), m.description[:60]] for n, m in enrichers.items()],
            ["nom", "ordre", "description"],
        ))
    return 0


def cmd_crawl(args) -> int:
    from scrapy.crawler import CrawlerProcess

    from jobs_scrape import registry

    try:
        meta = registry.get_source(args.source)
    except KeyError as exc:
        print(str(exc).strip('"'), file=sys.stderr)
        return 2

    missing = meta.missing_env()
    if missing:
        print(
            f"'{args.source}' requiert : {', '.join(missing)}. "
            f"Definissez ces variables d'environnement puis relancez.",
            file=sys.stderr,
        )
        return 2

    spider_args = dict(pair.split("=", 1) for pair in args.arg)
    if args.limit:
        spider_args["limit"] = str(args.limit)

    settings = _settings()
    if args.no_jsonl:
        settings.set("JSONL_ENABLED", False, priority="cmdline")
    if args.log_level:
        settings.set("LOG_LEVEL", args.log_level, priority="cmdline")

    process = CrawlerProcess(settings)
    process.crawl(meta.spider, **spider_args)
    process.start()
    return 0


def cmd_crawl_all(args) -> int:
    from scrapy.crawler import CrawlerProcess

    from jobs_scrape import registry

    sources = {
        name: meta for name, meta in registry.sources().items()
        if meta.enabled_by_default and not meta.missing_env()
    }
    if not sources:
        print("Aucun collecteur actif et pret a tourner.", file=sys.stderr)
        return 1

    print(f"Collecte de : {', '.join(sources)}")
    settings = _settings()
    if args.log_level:
        settings.set("LOG_LEVEL", args.log_level, priority="cmdline")

    process = CrawlerProcess(settings)
    spider_args = {"limit": str(args.limit)} if args.limit else {}
    for meta in sources.values():
        process.crawl(meta.spider, **spider_args)
    process.start()
    return 0


def cmd_search(args) -> int:
    from jobs_scrape import search

    conn = _connect()
    filters = {}
    for key in ("source", "region", "city", "company", "country", "contract_type"):
        value = getattr(args, key, None)
        if value:
            filters[key] = value
    if args.skill:
        filters["skills"] = args.skill
    if args.workload_min:
        filters["workload_min"] = args.workload_min
    if args.since:
        filters["posted_since"] = args.since

    results = search.search(conn, args.query, limit=args.limit, **filters)
    total = search.count(conn, args.query, **filters)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0

    if not results:
        print("Aucun resultat." + ("" if total else " La base est peut-etre vide."))
        return 0

    print(f"{len(results)} affichee(s) sur {total} resultat(s)\n")
    for row in results:
        location = " / ".join(x for x in (row.get("city"), row.get("region")) if x)
        print(f"  {row['title']}")
        meta = [row.get("company"), location, row.get("contract_type")]
        print(f"    {' | '.join(str(m) for m in meta if m)}")
        if row.get("skills"):
            print(f"    competences : {', '.join(row['skills'][:8])}")
        posted = row.get("posted_at") or row.get("first_seen_at", "")[:10]
        print(f"    {row['source']} | {posted} | {row['url']}")
        print()
    return 0


def cmd_terms(args) -> int:
    from jobs_scrape import search

    conn = _connect()
    filters = {k: v for k in ("source", "region") if (v := getattr(args, k, None))}
    rows = search.top_terms(conn, args.field, limit=args.top, **filters)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print(f"Aucun terme dans '{args.field}'. L'enrichisseur de mots-cles est-il installe ?")
        return 0
    print(_table([[r["value"], str(r["count"])] for r in rows], [args.field, "offres"]))
    return 0


def cmd_stats(args) -> int:
    from jobs_scrape import search

    conn = _connect()
    data = search.summary(conn)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    if not data["total"]:
        print("Base vide. Lancez une collecte : jobs-scrape crawl <source>")
        return 0

    print(f"{data['total']} offre(s) | {data['sources']} source(s) | "
          f"{data['companies']} entreprise(s)")
    print(f"periode : {data['oldest']} -> {data['newest']} | "
          f"{data['geolocated']} geolocalisee(s)")
    print("\nPar source")
    print(_table([[r["value"], str(r["count"])] for r in data["by_source"]],
                 ["source", "offres"]))
    if data["by_country"]:
        print("\nPar pays")
        print(_table([[r["value"], str(r["count"])] for r in data["by_country"]],
                     ["pays", "offres"]))
    return 0


def cmd_modules(args) -> int:
    from importlib.metadata import distributions

    from jobs_scrape import modules, registry

    specs = modules.load_manifest(args.manifest)

    if args.modules_action == "sync":
        print(f"Synchronisation depuis {args.manifest}")
        ok, failed = modules.sync(
            args.manifest, only=args.only or None,
            persist=args.persist, dry_run=args.dry_run,
        )
        if args.dry_run:
            return 0
        print(f"\n{ok} module(s) installe(s), {failed} echec(s)")
        if not args.persist and ok:
            print("Note : 'uv sync' aligne strictement l'environnement sur le "
                  "verrou et retirera ces modules. Relancez alors cette commande, "
                  "ou utilisez --persist pour les inscrire dans pyproject.toml.")
        return 1 if failed else 0

    installed = {d.metadata["Name"].lower().replace("_", "-") for d in distributions()}
    known = set(registry.sources()) | set(registry.enrichers())

    if not specs:
        print(f"Aucun module declare dans {args.manifest}")
        return 0

    rows = []
    for spec in specs:
        origin = spec.path or (spec.repo or "?")
        if spec.path:
            origin = f"local:{spec.path}"
        elif spec.repo:
            origin = spec.repo.rsplit("/", 1)[-1].removesuffix(".git") + f"@{spec.ref}"
        present = (
            spec.name in known
            or f"jobs-scrape-mod-{spec.name}" in installed
            or f"jobs-scrape-{spec.name}" in installed
        )
        rows.append([
            spec.name,
            "actif" if spec.enabled else "desactive",
            "installe" if present else "absent",
            origin[:52],
        ])
    print(_table(rows, ["module", "declare", "environnement", "origine"]))
    notes = [(s.name, s.note) for s in specs if s.note]
    if notes:
        print("\nNotes :")
        for name, note in notes:
            print(f"  {name} : {note}")
    return 0


# ------------------------------------------------------------------- point d'entree


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jobs-scrape",
        description="Collecte, enrichissement et exploration d'offres d'emploi FR/CH.",
    )
    parser.add_argument("--version", action="version", version=f"jobs-scrape {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="modules installes et leur etat")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("crawl", help="lancer un collecteur")
    p.add_argument("source")
    p.add_argument("--limit", type=int, help="s'arreter apres N offres")
    p.add_argument("-a", "--arg", action="append", default=[], metavar="CLE=VALEUR",
                   help="argument transmis au spider (repetable)")
    p.add_argument("--no-jsonl", action="store_true", help="ecrire en base seulement")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.set_defaults(func=cmd_crawl)

    p = sub.add_parser("crawl-all", help="lancer tous les collecteurs actifs")
    p.add_argument("--limit", type=int, help="par collecteur")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.set_defaults(func=cmd_crawl_all)

    p = sub.add_parser("search", help="chercher dans les offres collectees")
    p.add_argument("query", nargs="?", default=None,
                   help="termes ; omis, affiche les plus recentes")
    p.add_argument("--source")
    p.add_argument("--region", help="canton CH ou departement FR")
    p.add_argument("--city")
    p.add_argument("--company")
    p.add_argument("--country")
    p.add_argument("--contract-type")
    p.add_argument("--skill", action="append", default=[], help="repetable, cumulatif")
    p.add_argument("--workload-min", type=int, help="taux d'activite minimal, en %%")
    p.add_argument("--since", help="publiees depuis cette date (AAAA-MM-JJ)")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("terms", help="mots-cles ou competences les plus frequents")
    p.add_argument("--field", default="skills",
                   choices=["skills", "keywords", "languages", "occupations"])
    p.add_argument("--top", type=int, default=30)
    p.add_argument("--source")
    p.add_argument("--region")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_terms)

    p = sub.add_parser("stats", help="vue d'ensemble du corpus")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("modules", help="gerer les modules")
    p.add_argument("modules_action", nargs="?", default="list", choices=["list", "sync"])
    p.add_argument("--manifest", default="config/modules.yml")
    p.add_argument("--only", action="append", default=[], help="restreindre a ces modules")
    p.add_argument("--persist", action="store_true",
                   help="inscrire dans pyproject.toml (uv add) au lieu d'installer seulement")
    p.add_argument("--dry-run", action="store_true", help="afficher les commandes sans les lancer")
    p.set_defaults(func=cmd_modules)

    return parser


def main(argv: list[str] | None = None) -> int:
    import logging

    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
