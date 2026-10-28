"""The paintings: keys, prompts, credits, the make() call through a fake fal
client, and fetch() with pictures on, against app.artwork when a Tesserae
checkout is beside this repo and against the widget's stand-in otherwise."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from conftest import MELB


def test_keys(server):
    P = server.P
    assert (
        P.key_for("Arctotheca calendula", "pressed")
        == "arctotheca_calendula--pressed--p1"
    )
    assert (
        P.key_for("Arctotheca calendula", "nonsense")
        == "arctotheca_calendula--pressed--p1"
    )
    assert (
        P.key_for("Trifolium repens", "cyanotype", "nano_banana_pro")
        == "trifolium_repens--cyanotype--p1--nano_banana_pro"
    )


def test_prompt_asks_for_a_pressed_plant_on_bare_paper(server):
    P = server.P
    for style in P.STYLES:
        text = P.prompt_for(
            {"style": style, "common": "Capeweed", "sci": "Arctotheca calendula"}
        )
        assert "Capeweed (Arctotheca calendula)" in text
        for must in (
            "pressed flat",
            "stems, leaves and flowers",
            "roots if the plant is small",
            "no label",
            "no tape",
            "no text",
            "no shadow",
            "top-down",
        ):
            assert must in text, (style, must)
        if style == "cyanotype":
            assert "Prussian blue paper" in text and "white silhouette" in text
        else:
            assert "white paper" in text
    assert P.BLUE_PAPER == {"cyanotype": "#1d3a6b"}


def test_credit_names_model_photographer_and_licence(server):
    P = server.P
    assert (
        P.credit_for("nano_banana", "Audrey F", "CC BY-NC")
        == "AI painting (Nano Banana on fal.ai) from a photo by Audrey F (CC BY-NC)"
    )
    assert (
        P.credit_for("nano_banana_pro", "", "")
        == "AI painting (Nano Banana Pro on fal.ai) from an iNaturalist photo"
    )


def test_make_paints_from_the_photo(server):
    P = server.P
    seen = {}

    def generate(model, prompt, *, refs, aspect, retries=0):
        seen.update(model=model, prompt=prompt, refs=list(refs), aspect=aspect)
        return b"\xff\xd8jpeg"

    job = SimpleNamespace(
        key="capeweed--pressed--p1",
        payload={
            "style": "pressed",
            "photo": "https://x/medium.jpg",
            "common": "Capeweed",
            "sci": "Arctotheca calendula",
            "by": "Audrey F",
            "licence": "CC BY-NC",
            "model": "nano_banana",
        },
        fal=SimpleNamespace(generate=generate),
        stop=threading.Event(),
    )
    raw, meta = P.make(job)
    assert raw.startswith(b"\xff\xd8")
    assert (
        seen["model"] == "nano_banana"
        and seen["refs"] == ["https://x/medium.jpg"]
        and seen["aspect"] == "3:4"
    )
    assert meta["credit"].startswith(
        "AI painting (Nano Banana on fal.ai) from a photo by Audrey F"
    )
    assert meta["style"] == "pressed" and meta["sci"] == "Arctotheca calendula"
    job.payload["photo"] = ""
    with pytest.raises(Exception, match="no openly licensed photo"):
        P.make(job)


def test_fetch_with_paintings_shows_photos_until_they_land(
    server, fake_inat, tmp_path, monkeypatch
):
    """Without a key nothing paints: the photos show, the foot says why, and
    the sheet does not ask to be refreshed. On a host with app.artwork the
    note is the standard no-key sentence; on the stand-in it says the host
    is too old."""
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FAL_API_KEY", raising=False)
    ctx = {
        "data_dir": str(tmp_path),
        "preview": False,
        "settled": True,
        "cell_id": "t1",
    }
    d = server.fetch(
        {**MELB, "pictures": "gen", "style": "cyanotype", "count": "2"}, {}, ctx=ctx
    )
    assert "error" not in d
    assert d["style"] == "cyanotype" and d["blue"] == "#1d3a6b"
    assert d["style_label"] == "Cyanotype after Anna Atkins"
    for r in d["species"]:
        assert r["pic"] == "" and r["state"] in ("no_key", "no_host")
    assert d["notes"], "the foot says why nothing is painted"
    assert d["live_refresh_s"] == 0 and d["live_pending"] == 0


def test_look_options_are_bounded(server):
    look = server._look(
        {
            "pictures": "free",
            "style": "cyanotype",
            "paper": "velvet",
            "panel": "mono",
            "title": " Flora ",
            "credits": False,
        }
    )
    assert look["style"] == "" and look["blue"] == "" and look["paper"] == "cream"
    assert (
        look["panel"] == "mono"
        and look["title"] == "Flora"
        and look["credits"] is False
    )
    assert (
        server._int("6", 3, server.COUNTS) == 6
        and server._int("5", 3, server.COUNTS) == 3
    )
    assert server._int("x", 10, server.RADII) == 10


def test_flatten_lifts_the_paper_to_white(server):
    """A painting on warm grey paper comes back on white, the plant kept."""
    import io

    from PIL import Image, ImageDraw

    im = Image.new("RGB", (120, 160), (200, 190, 170))
    ImageDraw.Draw(im).ellipse((30, 40, 90, 120), fill=(60, 90, 40))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=95)
    out = Image.open(io.BytesIO(server.P.flatten(buf.getvalue()))).convert("RGB")
    assert out.size == (120, 160)
    assert min(out.getpixel((3, 3))) >= 250, "the paper is white"
    r, g, b = out.getpixel((60, 80))
    assert g > r and g > b and g < 160, "the plant keeps its green"
    # a dark edge is not paper: left alone
    dark = Image.new("RGB", (40, 40), (30, 30, 30))
    buf = io.BytesIO()
    dark.save(buf, "JPEG")
    assert server.P.flatten(buf.getvalue()) == buf.getvalue()
