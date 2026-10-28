"""Herbarium Sheet: the plants in flower or fruit around the panel right
now, as a herbarium sheet of pressed specimens with labels, an
institutional label block and a stamp.

The data is iNaturalist's research-grade plant observations with an openly
licensed photo, near a place (or by one user) in a window, ranked by how
many records each species has; the sheet shows the top few. The species list
is kept for six hours per cell. Pictures are the records' own photographs,
or AI paintings through Tesserae's ``app.artwork`` when the user opts in and
a fal.ai key is set. Helper modules beside this file are loaded by path.
Never raises: an error is {"error": "..."} with enough of the look for the
page to still draw as paper."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
logger = logging.getLogger("tesserae.herbarium_sheet")


def _sibling(name: str) -> Any:
    full = f"_tesserae_plugins.herbarium_sheet.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, HERE / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


INAT = _sibling("inat")
P = _sibling("paint")

CACHE_S = 6 * 3600
COUNTS = (1, 2, 3, 4, 6)
RADII = (2, 5, 10, 25, 50)
PAPERS = ("cream", "white", "aged")
PANELS = ("colour", "gray16", "gray4", "mono")
LAYOUTS = ("mounted", "plate")
# pixels on the painting's long side, by how many share the page
PAINT_PX = {1: 1000, 2: 800, 3: 640, 4: 560, 6: 480}


def _int(value: Any, default: int, allowed: tuple[int, ...] | None = None) -> int:
    try:
        n = int(float(str(value)))
    except (TypeError, ValueError):
        return default
    if allowed is not None and n not in allowed:
        return default
    return n


def _choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    s = str(value if value is not None else "").strip()
    return s if s in allowed else default


def _place(options: dict[str, Any]) -> tuple[float, float] | None:
    try:
        lat = float(options.get("latitude"))
        lon = float(options.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def _label(options: dict[str, Any]) -> str:
    loc = options.get("location")
    if isinstance(loc, dict) and loc.get("label"):
        return str(loc["label"]).strip()
    return str(
        options.get("label") or (loc if isinstance(loc, str) else "") or ""
    ).strip()


def _cache_key(parts: list[Any]) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _cached(path: Path) -> dict[str, Any] | None:
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(got, dict) or time.time() - float(got.get("at") or 0) > CACHE_S:
        return None
    return got.get("data") if isinstance(got.get("data"), dict) else None


def _keep(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"at": time.time(), "data": data}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.warning("herbarium_sheet: could not write the cache at %s", path)


def accession(today: date, subject: str) -> str:
    """'2026.10.003': the year and month of the sheet, then a number from the
    sheet's own identity, so each cell keeps its number through the month."""
    n = (
        int(
            hashlib.sha1(subject.encode("utf-8"), usedforsecurity=False).hexdigest()[
                :6
            ],
            16,
        )
        % 999
        + 1
    )
    return f"{today.year}.{today.month:02d}.{n:03d}"


def month_name(today: date) -> str:
    return today.strftime("%B %Y")


def latest_text(iso: str) -> str:
    """'12 Oct' for a date this year, '12 Oct 2024' otherwise, '' for none."""
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return ""
    return (
        d.strftime("%-d %b") if d.year == date.today().year else d.strftime("%-d %b %Y")
    )


def _look(options: dict[str, Any]) -> dict[str, Any]:
    pictures = _choice(options.get("pictures"), ("free", "gen"), "free")
    style = P.style_id(options.get("style"))
    return {
        "layout": _choice(options.get("layout"), LAYOUTS, "mounted"),
        "paper": _choice(options.get("paper"), PAPERS, "cream"),
        "panel": _choice(options.get("panel"), PANELS, "colour"),
        "pictures": pictures,
        "style": style if pictures == "gen" else "",
        "style_label": P.style_of(style)[0] if pictures == "gen" else "",
        "blue": P.BLUE_PAPER.get(style, "") if pictures == "gen" else "",
        "title": str(options.get("title") or "").strip() or "HERBARIUM",
        "credits": options.get("credits", True) is not False,
    }


def fetch(
    options: dict[str, Any], settings: dict[str, Any], *, ctx: dict[str, Any]
) -> dict[str, Any]:
    look = _look(options)
    source = _choice(options.get("source"), ("place", "user"), "place")
    login = str(options.get("user_login") or "").strip().lstrip("@")
    radius = _int(options.get("radius_km"), 10, RADII)
    window = _choice(options.get("window"), INAT.WINDOWS, "month")
    count = _int(options.get("count"), 3, COUNTS)
    if look["layout"] == "plate":
        count = 1
    place = _place(options)
    label = _label(options)
    today = date.today()

    if source == "user":
        if not login:
            return {
                **look,
                "error": "Set an iNaturalist username in this cell's settings.",
            }
        place = None
        where = f"Collected by {login}"
        head = label or login
    else:
        if place is None:
            return {
                **look,
                "error": "Set a location in this cell's settings, or in Settings for the app.",
            }
        where = f"Collected within {radius} km"
        head = (
            label
            or f"{abs(place[0]):.2f}°{'S' if place[0] < 0 else 'N'}, {abs(place[1]):.2f}°{'E' if place[1] >= 0 else 'W'}"
        )

    subject = _cache_key([source, login, place, radius, window, count])
    data_dir = Path(ctx.get("data_dir") or ".")
    cache = data_dir / "cache" / f"{subject}.json"
    got = None if ctx.get("fresh") else _cached(cache)
    if got is None:
        got, err = INAT.specimens(place, radius, login, window, count, today)
        if got is None:
            stale = _cached_any_age(cache)
            if stale is None:
                return {**look, "error": err or INAT.ERR_UNREACHABLE}
            got = stale
        else:
            _keep(cache, got)

    rows = [dict(r) for r in got.get("species") or []][:count]
    for r in rows:
        r["latest_text"] = latest_text(str(r.get("latest") or ""))
        r["pic"] = ""
        r["credit"] = ""
        r["state"] = "photo"

    notes: list[str] = []
    live = {"live_refresh_s": 0, "live_pending": 0}
    if look["pictures"] == "gen" and rows:
        model = P.model_of(options.get("model"))
        art = P.ART.open(ctx, settings, subject=f"{subject}-{look['style']}")
        px = PAINT_PX.get(count, 640)
        for r in rows:
            if not r.get("sci"):
                continue
            key = P.key_for(r["sci"], look["style"], model)
            payload = {
                "style": look["style"],
                "photo": r.get("photo") or "",
                "common": r.get("common") or "",
                "sci": r["sci"],
                "by": r.get("by") or "",
                "licence": r.get("licence") or "",
                "model": model,
            }
            gotp = art.request(
                key,
                payload,
                title=f"{r.get('common') or r['sci']}, {look['style_label']}",
            )
            r["state"] = gotp.state
            if gotp.ready:
                variant = "" if look["blue"] else P.flat_variant(key, gotp.path)
                src = art.url(key, px=px, levels=look["panel"], variant=variant)
                if src:
                    r["pic"] = src
                    r["credit"] = gotp.credit
                    r["state"] = "painted"
        art.finish(ctx, facet=look["style"])
        notes = art.notes()
        live = art.live()
        logger.info(
            "herbarium_sheet: %s render, %d species, painted %d, started %d, held %d, capped %d, no key %d, failed %d",
            "preview" if ctx.get("preview") else "panel",
            len(rows),
            art.states.get("ready", 0),
            art.started,
            art.states.get("held", 0),
            art.states.get("capped", 0),
            art.states.get("no_key", 0),
            art.states.get("failed", 0),
        )

    window_text = {
        "month": "in flower this month",
        "30d": "the last 30 days",
        "90d": "the last 90 days",
    }[window]
    return {
        **look,
        "head": head,
        "where": where,
        "window": window,
        "window_text": window_text,
        "month": month_name(today),
        "accession": accession(today, subject),
        "radius_km": radius,
        "count": count,
        "species": rows,
        "species_total": int(got.get("species_total") or len(rows)),
        "notes": notes,
        **live,
    }


def _cached_any_age(path: Path) -> dict[str, Any] | None:
    """The last answer, however old, for when iNaturalist is down."""
    try:
        got = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return (
        got.get("data")
        if isinstance(got, dict) and isinstance(got.get("data"), dict)
        else None
    )
