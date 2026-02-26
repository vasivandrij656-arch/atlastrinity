import os
import subprocess
from unittest.mock import Mock

from src.maintenance import setup_dev as s


def test_brew_formula_installed(monkeypatch):
    # Simulate brew list --formula returning 0
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Mock(returncode=0))
    assert s._brew_formula_installed("postgresql@17")

    # Simulate non-zero return
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Mock(returncode=1))
    assert not s._brew_formula_installed("postgresql@17")


def test_brew_cask_installed_brew(monkeypatch, tmp_path):
    # brew lists cask installed
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Mock(returncode=0))
    assert s._brew_cask_installed("docker", "Docker")


def test_brew_cask_installed_app_path(monkeypatch, tmp_path):
    # brew reports not installed but app exists in /Applications
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Mock(returncode=1))
    # fake app path
    monkeypatch.setattr(os.path, "exists", lambda p: "Docker.app" in p)
    assert s._brew_cask_installed("docker", "Docker")


def test_brew_cask_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Mock(returncode=1))
    monkeypatch.setattr(os.path, "exists", lambda p: False)
    assert not s._brew_cask_installed("docker", "Docker")
