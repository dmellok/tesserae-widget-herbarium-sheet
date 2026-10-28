"""Loads server.py by path the way the host does. ``app.artwork`` (the paintings)
is only there when a Tesserae checkout sits beside this repo or TESSERAE_REPO
points at one; without it the widget's own stand-in is what gets tested."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path

import pytest

MELB = {"latitude": -37.81, "longitude": 144.96, "location": {"label": "Melbourne"}}

ROOT = Path(__file__).resolve().parents[1]
_TESSERAE = Path(os.environ.get("TESSERAE_REPO") or ROOT.parent / "tesserae")
if (_TESSERAE / "app").is_dir() and str(_TESSERAE) not in sys.path:
    sys.path.insert(0, str(_TESSERAE))


def _load():
    spec = importlib.util.spec_from_file_location(
        "herbarium_server", ROOT / "server.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def server():
    return _load()


@pytest.fixture
def offline(monkeypatch):
    """Every urlopen fails as if there were no network."""
    import urllib.error
    import urllib.request

    def no_net(*a, **k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", no_net)
    return no_net


class _Resp:
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self, n=-1):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _taxon(tid, name, common, count):
    return {
        "count": count,
        "taxon": {
            "id": tid,
            "name": name,
            "preferred_common_name": common,
            "default_photo": {
                "medium_url": f"https://static.inaturalist.org/photos/{tid}/medium.jpg",
                "license_code": "cc-by",
                "attribution": "(c) Default Person, some rights reserved (CC BY)",
            },
        },
    }


def _obs(tid, when, login, lic="cc-by-nc", name=None):
    return {
        "observed_on": when,
        "taxon": {"id": tid},
        "user": {"login": login, "name": name},
        "photos": [
            {
                "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
                "license_code": None,
            },
            {
                "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/2/square.jpg",
                "license_code": lic,
                "attribution": f"(c) {login}, some rights reserved",
            },
        ],
    }


SPECIES = {
    "total_results": 3,
    "results": [
        _taxon(1, "Arctotheca calendula", "Capeweed", 60),
        _taxon(2, "Plantago lanceolata", "ribwort plantain", 57),
        _taxon(3, "Trifolium repens", "white clover", 57),
    ],
}
OBS = {
    1: {"results": [_obs(1, "2026-10-28", "audrey", name="Audrey F")]},
    2: {"results": [_obs(2, "2026-10-13", "pvesk")]},
    3: {"results": []},
}


@pytest.fixture
def fake_inat(monkeypatch):
    calls = []

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        calls.append(url)
        if "species_counts" in url:
            return _Resp(SPECIES)
        tid = int(url.split("taxon_id=")[1].split("&")[0])
        return _Resp(OBS[tid])

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return calls
