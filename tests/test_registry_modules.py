"""Registre et manifeste : le coeur doit fonctionner sans aucun module."""

import pytest
import yaml

from jobs_scrape import modules, registry


def test_le_registre_repond_quel_que_soit_l_environnement():
    """Le coeur doit fonctionner avec zero module comme avec dix.

    Ce test tournait initialement en supposant un environnement vide ; il
    echouait des qu'un collecteur etait installe a cote, ce qui est pourtant le
    cas normal a l'usage. On verifie donc le contrat, pas le contenu.
    """
    from jobs_scrape.source import EnricherMeta, SourceMeta

    sources = registry.sources()
    assert isinstance(sources, dict)
    assert all(isinstance(meta, SourceMeta) for meta in sources.values())
    assert all(name == meta.name for name, meta in sources.items())

    enrichers = registry.enrichers()
    assert isinstance(enrichers, dict)
    assert all(isinstance(meta, EnricherMeta) for meta in enrichers.values())


def test_erreur_de_source_inconnue_est_actionnable():
    with pytest.raises(KeyError) as excinfo:
        registry.get_source("inexistant")
    assert "modules sync" in str(excinfo.value)


def test_manifeste_absent_vaut_aucun_module(tmp_path):
    assert modules.load_manifest(tmp_path / "rien.yml") == []


def test_lecture_du_manifeste(tmp_path):
    path = tmp_path / "modules.yml"
    path.write_text(yaml.safe_dump({"modules": [
        {"name": "jobroom", "repo": "git+ssh://git@github.com/u/r.git", "ref": "main"},
        {"name": "indeed", "repo": "https://github.com/u/i.git",
         "enabled": False, "note": "bloque par le pare-feu du site"},
        {"name": "local", "path": "../mod-local", "config": {"backend": "taxonomy"}},
    ]}), encoding="utf-8")

    specs = modules.load_manifest(path)
    assert [s.name for s in specs] == ["jobroom", "indeed", "local"]
    assert specs[1].enabled is False
    assert specs[2].is_local
    assert modules.module_config(path) == {"local": {"backend": "taxonomy"}}


def test_requirement_prefixe_les_url_git(tmp_path):
    spec = modules.ModuleSpec(name="x", repo="https://github.com/u/r.git", ref="v1")
    assert spec.requirement() == "git+https://github.com/u/r.git@v1"

    ssh = modules.ModuleSpec(name="x", repo="git+ssh://git@github.com/u/r.git")
    assert ssh.requirement() == "git+ssh://git@github.com/u/r.git@main"


def test_requirement_exige_une_origine():
    with pytest.raises(ValueError):
        modules.ModuleSpec(name="x").requirement()


def test_cles_inconnues_du_manifeste_sont_ignorees(tmp_path):
    path = tmp_path / "m.yml"
    path.write_text(yaml.safe_dump({"modules": [{"name": "x", "path": ".", "typo": 1}]}))
    assert modules.load_manifest(path)[0].name == "x"


def test_l_echec_d_installation_porte_sa_cause(monkeypatch, capsys, tmp_path):
    """Un « voir le journal » ne laisse rien a l'utilisateur.

    Les echecs les plus frequents sont transitoires : la sortie doit nommer le
    module, montrer la cause, et donner la commande qui relance ce module-la.
    """
    import subprocess

    manifest = tmp_path / "m.yml"
    manifest.write_text(yaml.safe_dump({"modules": [
        {"name": "cassé", "repo": "https://github.com/u/absent.git"},
    ]}), encoding="utf-8")

    def echec(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="fatal: dépôt introuvable")

    monkeypatch.setattr(subprocess, "run", echec)
    ok, failed = modules.sync(manifest)

    assert (ok, failed) == (0, 1)
    sortie = capsys.readouterr().err
    assert "dépôt introuvable" in sortie          # la cause reelle
    assert "--only cassé" in sortie               # la commande qui relance
