"""Registre et manifeste : le coeur doit fonctionner sans aucun module."""

import pytest
import yaml

from jobs_scrape import modules, registry


def test_registre_vide_par_defaut():
    """Aucun module installe en test : le coeur reste utilisable."""
    assert registry.sources() == {}
    assert registry.enrichers() == {}


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
