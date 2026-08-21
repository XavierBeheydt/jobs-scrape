"""Manifeste des modules et installation depuis GitHub.

Les collecteurs vivent dans des depots separes -- notamment pour qu'un module
dont les conditions d'utilisation sont restrictives puisse rester prive sans
entrainer le reste du projet. ``config/modules.yml`` decrit lesquels installer,
et ``jobs-scrape modules sync`` s'en charge.

Les depots prives passent par ``git+ssh``. C'est deliberé : l'authentification
SSH de ``gh`` est deja en place sur la machine, donc rien a configurer et aucun
jeton a stocker dans un fichier de configuration.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_MANIFEST = Path("config/modules.yml")


@dataclass
class ModuleSpec:
    """Une entree du manifeste."""

    name: str
    repo: str | None = None
    """URL git. Prefixer par ``git+ssh://`` pour un depot prive."""

    path: str | None = None
    """Chemin local. Prime sur ``repo`` : c'est l'echappatoire pour developper
    un module et le voir pris en compte sans passer par un commit."""

    ref: str = "main"
    enabled: bool = True
    editable: bool = False
    config: dict[str, Any] = field(default_factory=dict)
    """Options transmises au module -- par exemple le backend d'un enrichisseur."""

    note: str = ""

    @property
    def is_local(self) -> bool:
        return bool(self.path)

    def requirement(self) -> str:
        """Specification d'installation comprise par ``uv pip install``.

        Une URL de depot doit porter le prefixe ``git+``, faute de quoi pip la
        prend pour une archive a telecharger. On le pose donc soi-meme plutot
        que d'imposer a l'utilisateur de l'ecrire dans le manifeste.
        """
        if self.path:
            return str(Path(self.path).expanduser())
        if not self.repo:
            raise ValueError(f"module '{self.name}' : ni 'repo' ni 'path' renseigne")

        url = self.repo
        # Forme abregee de GitHub : git@github.com:utilisateur/depot.git
        if url.startswith("git@") and ":" in url:
            host, _, repo_path = url[4:].partition(":")
            url = f"ssh://git@{host}/{repo_path}"

        is_repository = url.endswith(".git") or url.startswith(("ssh://", "git://"))
        if is_repository and not url.startswith("git+"):
            url = f"git+{url}"

        # Une reference deja presente dans l'URL prime sur le champ ``ref``.
        if self.ref and "@" not in url.rsplit("/", 1)[-1]:
            url = f"{url}@{self.ref}"
        return url


def load_manifest(path: str | Path = DEFAULT_MANIFEST) -> list[ModuleSpec]:
    """Lit le manifeste. Un fichier absent equivaut a « aucun module »."""
    path = Path(path)
    if not path.exists():
        logger.debug("manifeste absent (%s) : aucun module declare", path)
        return []

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = data.get("modules") or []
    specs: list[ModuleSpec] = []
    for entry in entries:
        if isinstance(entry, str):
            entry = {"name": entry}
        known = {f for f in ModuleSpec.__dataclass_fields__}
        unknown = set(entry) - known
        if unknown:
            logger.warning(
                "module '%s' : cle(s) inconnue(s) ignoree(s) : %s",
                entry.get("name", "?"), ", ".join(sorted(unknown)),
            )
        specs.append(ModuleSpec(**{k: v for k, v in entry.items() if k in known}))
    return specs


def module_config(path: str | Path = DEFAULT_MANIFEST) -> dict[str, dict[str, Any]]:
    """Options par module, telles que declarees dans le manifeste."""
    return {spec.name: spec.config for spec in load_manifest(path) if spec.config}


def _uv() -> str:
    executable = shutil.which("uv")
    if not executable:
        raise RuntimeError(
            "'uv' est introuvable dans le PATH. Installation : "
            "curl -LsSf https://astral.sh/uv/install.sh | sh"
        )
    return executable


def install(spec: ModuleSpec, *, persist: bool = False, dry_run: bool = False) -> bool:
    """Installe un module. Renvoie ``True`` si l'operation a reussi.

    Par defaut on utilise ``uv pip install``, qui pose le module dans
    l'environnement sans modifier ``pyproject.toml`` -- le depot reste propre.
    Revers de la medaille : un ``uv sync`` ulterieur, qui aligne strictement
    l'environnement sur le fichier de verrouillage, les retirera. Il suffit de
    relancer la synchronisation.

    ``persist=True`` passe par ``uv add`` : le module entre dans les dependances
    et survit a ``uv sync``, au prix d'une modification de ``pyproject.toml``.
    """
    requirement = spec.requirement()
    if persist:
        command = [_uv(), "add", requirement]
    else:
        command = [_uv(), "pip", "install"]
        if spec.editable and spec.is_local:
            command.append("--editable")
        command.append(requirement)

    if dry_run:
        print("  " + " ".join(command))
        return True

    logger.info("installation de '%s' depuis %s", spec.name, requirement)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(
            "echec de l'installation de '%s' :\n%s",
            spec.name, (result.stderr or result.stdout).strip(),
        )
        return False
    return True


def sync(
    path: str | Path = DEFAULT_MANIFEST,
    *,
    only: list[str] | None = None,
    persist: bool = False,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Installe tous les modules actives du manifeste.

    Renvoie ``(reussis, echoues)``. Un module qui echoue n'interrompt pas les
    autres : mieux vaut neuf collecteurs sur dix qu'aucun.
    """
    specs = load_manifest(path)
    if not specs:
        print(f"Aucun module declare dans {path}")
        return 0, 0

    succeeded = failed = 0
    for spec in specs:
        if only and spec.name not in only:
            continue
        if not spec.enabled and not only:
            reason = f" ({spec.note})" if spec.note else ""
            print(f"  - {spec.name} : desactive{reason}")
            continue
        if install(spec, persist=persist, dry_run=dry_run):
            succeeded += 1
            if not dry_run:
                print(f"  + {spec.name}")
        else:
            failed += 1
            print(f"  ! {spec.name} : echec (voir le journal)", file=sys.stderr)

    if not dry_run:
        from jobs_scrape import registry

        registry.clear_cache()
    return succeeded, failed
