"""The options panel stays short: a handful of options up front, the rest
nested under the choice they depend on or under More options."""

from __future__ import annotations

import json
from pathlib import Path

MANIFEST = json.loads(
    (Path(__file__).resolve().parent.parent / "plugin.json").read_text(encoding="utf-8")
)
OPTIONS = MANIFEST["cell_options"]

ORDER = [
    "source",
    "user_login",
    "location",
    "radius_km",
    "window",
    "layout",
    "count",
    "pictures",
    "style",
    "paper",
    "model",
    "panel",
    "title",
    "credits",
]
UP_FRONT = ["source", "window", "layout", "pictures", "paper"]


def _up_front(o: dict) -> bool:
    return not o.get("show_if") and not o.get("advanced")


def test_manifest_basics() -> None:
    assert MANIFEST["name"] == "Herbarium Sheet"
    assert MANIFEST["icon"] == "ph-plant" and MANIFEST["category"] == "art"
    assert MANIFEST["requires"] == ["network:*"]
    assert (
        MANIFEST["render"]["needs_network"] is True
        and MANIFEST["render"]["warm_ahead_s"] == 150
    )
    assert MANIFEST["tesserae_min"] == "0.463.0"
    assert not any(o["name"] == "label" for o in OPTIONS)


def test_option_names_and_order() -> None:
    assert [o["name"] for o in OPTIONS] == ORDER


def test_few_options_up_front() -> None:
    assert [o["name"] for o in OPTIONS if _up_front(o)] == UP_FRONT
    assert len(UP_FRONT) <= 5


def test_show_if_refers_to_real_options() -> None:
    names = {o["name"] for o in OPTIONS}
    for o in OPTIONS:
        for key in o.get("show_if") or {}:
            assert key in names, (o["name"], key)


def test_advanced_options_come_last() -> None:
    seen = False
    for o in OPTIONS:
        if o.get("advanced"):
            seen = True
        else:
            assert not seen, f"{o['name']} follows an advanced option"


def test_styles_and_models_match_the_code() -> None:
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "herbarium_paint_m", root / "paint.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    styles = next(o for o in OPTIONS if o["name"] == "style")
    assert [c["value"] for c in styles["choices"]] == list(mod.STYLES)
    assert [c["label"] for c in styles["choices"]] == [
        v[0] for v in mod.STYLES.values()
    ]
    models = next(o for o in OPTIONS if o["name"] == "model")
    assert [c["value"] for c in models["choices"]] == list(mod.MODEL_LABELS)


def test_no_em_dashes_anywhere() -> None:
    dash = chr(0x2014)
    text = json.dumps(MANIFEST, ensure_ascii=False)
    assert dash not in text
    for name in (
        "README.md",
        "client.js",
        "client.css",
        "server.py",
        "inat.py",
        "paint.py",
    ):
        p = Path(__file__).resolve().parent.parent / name
        if p.exists():
            assert dash not in p.read_text(encoding="utf-8"), name
