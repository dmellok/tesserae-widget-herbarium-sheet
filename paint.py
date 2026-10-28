"""AI paintings for the Herbarium Sheet: each species painted once per style
from its iNaturalist photo, through Tesserae's ``app.artwork`` (the store,
the budget, the queue, the hold while a dashboard is being edited and the
pictures page all come from the host). Loaded by server.py by path.

On a Tesserae older than 0.463 ``app.artwork`` is missing: the collection is
a stand-in that answers ``no_host`` for every picture, the sheet shows the
photographs, and a note at the foot says why."""

from __future__ import annotations

import re
from typing import Any

try:
    from app import artwork  # Tesserae 0.463+
except ImportError:
    artwork = None  # type: ignore[assignment]

try:
    from app import fal as _fal
except ImportError:
    _fal = None  # type: ignore[assignment]

NEEDS_HOST = "AI paintings need Tesserae 0.463 or later; this server is older, so the photographs show."
PROMPT_VERSION = 1
WHITE_POINT = 232
DEFAULT_MODEL = "nano_banana"
# Labels for the credit line when app.fal is not there to ask.
MODEL_LABELS = {
    "nano_banana": "Nano Banana",
    "nano_banana_pro": "Nano Banana Pro",
    "flux_kontext": "FLUX.1 Kontext Pro",
    "gpt_image": "GPT Image 2",
    "seedream": "Seedream 4",
}

# style id -> (label, how it is drawn, the paper it is on)
STYLES: dict[str, tuple[str, str, str]] = {
    "pressed": (
        "Pressed specimen",
        "A photograph of a real pressed and dried herbarium specimen, the plant itself and not a drawing: "
        "its colours muted and faded as a dried plant's are, the leaves papery, thin and flat, every part pressed flat to the paper",
        "pure white paper, evenly lit",
    ),
    "redoute": (
        "Watercolour after Redouté",
        "A botanical watercolour in the manner of Pierre-Joseph Redouté: delicate transparent washes over fine stipple, "
        "soft modelling, the colours true to life, the plant drawn as if pressed flat",
        "plain white paper",
    ),
    "inkwash": (
        "Ink and wash",
        "An ink and wash drawing in brush and dilute black ink: a few confident strokes for the stems, "
        "grey washes for the leaves and flowers, no colour, the plant laid flat",
        "plain white paper",
    ),
    "cyanotype": (
        "Cyanotype after Anna Atkins",
        "A cyanotype photogram in the manner of Anna Atkins: the plant as a pale white silhouette with soft edges, "
        "the finest veins and petals showing faintly where the light came through",
        "Prussian blue paper, the deep blue filling the whole picture edge to edge",
    ),
    "woodcut": (
        "Woodcut herbal, 1542",
        "A woodcut illustration from a printed herbal of 1542: bold black ink outlines with simple hatching, "
        "lightly hand-coloured in a few flat tints, the plant drawn flat as the old herbals drew it",
        "plain white paper",
    ),
}
DEFAULT_STYLE = "pressed"
# The styles whose picture is not on white paper, so the page keeps that colour behind them.
BLUE_PAPER = {"cyanotype": "#1d3a6b"}

PROMPT = (
    "{how}, of {common} ({sci}), made from the reference photo: the species' true leaves, flowers, "
    "colours and habit kept exactly, nothing invented. The whole plant pressed flat: stems, leaves and "
    "flowers, and the roots if the plant is small, laid out as a herbarium specimen and seen straight "
    "from above, top-down. On {paper}, which fills the whole picture edge to edge, and nothing else "
    "in the picture: no label, no tape, no text, no lettering, no shadow, no table, no sheet edge, "
    "no border, no frame."
)


class _NoArt:
    """What a collection opens to on a Tesserae without app.artwork."""

    key = ""
    preview = False
    settled = True
    cap = 0
    started = 0
    pending = 0
    busy = False

    def __init__(self) -> None:
        self.states: dict[str, int] = {"no_host": 0}

    def request(
        self, key: str, payload: dict[str, Any], *, title: str = "", want: bool = True
    ) -> Any:
        self.states["no_host"] += 1
        return _Got(key)

    def url(self, key: str, **kw: Any) -> str:
        return ""

    def live(self) -> dict[str, int]:
        return {"live_refresh_s": 0, "live_pending": 0}

    def notes(self) -> list[str]:
        return [NEEDS_HOST] if self.states.get("no_host") else []

    def status(self) -> list[str]:
        return []

    def finish(self, ctx: dict[str, Any], facet: str = "", extra: Any = None) -> None:
        return None


class _Got:
    ready = False
    state = "no_host"
    credit = ""
    why = NEEDS_HOST

    def __init__(self, key: str) -> None:
        self.key = key


class _NoCollection:
    """A Collection stand-in: opens to a _NoArt."""

    def __init__(self, name: str) -> None:
        self.name = name

    def open(
        self, ctx: dict[str, Any], settings: Any, *, subject: str = "", cell: str = ""
    ) -> _NoArt:
        return _NoArt()


def style_of(style: Any) -> tuple[str, str, str]:
    return STYLES.get(str(style or ""), STYLES[DEFAULT_STYLE])


def style_id(style: Any) -> str:
    s = str(style or "")
    return s if s in STYLES else DEFAULT_STYLE


def model_of(model: Any) -> str:
    m = str(model or "")
    if _fal is not None:
        return m if m in getattr(_fal, "EDIT_MODELS", ()) else DEFAULT_MODEL
    return m if m in MODEL_LABELS else DEFAULT_MODEL


def model_label(model: Any) -> str:
    m = model_of(model)
    if _fal is not None:
        try:
            return str(_fal.label_of(m))
        except Exception:
            pass
    return MODEL_LABELS.get(m, m)


def key_for(sci: str, style: Any, model: Any = DEFAULT_MODEL) -> str:
    """``<slug(sci)>--<style>--p1``, plus the model when it is not the default,
    so switching models never paints over what another made."""
    key = f"{_slug(sci)}--{style_id(style)}--p{PROMPT_VERSION}"
    m = model_of(model)
    if m != DEFAULT_MODEL:
        key += f"--{m}"
    return key


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:60] or "x"


def prompt_for(payload: dict[str, Any]) -> str:
    _label, how, paper = style_of(payload.get("style"))
    return PROMPT.format(
        how=how,
        common=str(payload.get("common") or payload.get("sci") or "the plant"),
        sci=str(payload.get("sci") or ""),
        paper=paper,
    )


def credit_for(model: Any, by: str, licence: str) -> str:
    who = f" from a photo by {by}" if by else " from an iNaturalist photo"
    lic = f" ({licence})" if licence else ""
    return f"AI painting ({model_label(model)} on fal.ai){who}{lic}"


def flatten(raw: bytes) -> bytes:
    """The painting with its paper lifted to white, as a PNG: the models paint
    'white paper' as a warm grey sheet, which multiplied over the page shows
    as a rectangle. The paper colour is the median of a thin band along the
    edges; each channel is scaled so that colour becomes white and the plant
    keeps its hue. Returns the input unchanged if Pillow is missing."""
    try:
        from PIL import Image, ImageOps, ImageStat
    except ImportError:  # pragma: no cover - Pillow ships with Tesserae
        return raw
    import io

    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert("RGB")
    except Exception:
        return raw
    w, h = im.size
    b = max(2, min(w, h) // 40)
    bands = [
        ImageStat.Stat(im.crop(box)).median
        for box in ((0, 0, w, b), (0, h - b, w, h), (0, 0, b, h), (w - b, 0, w, h))
    ]
    paper = [sorted(band[i] for band in bands)[len(bands) // 2] for i in range(3)]
    # a dark edge is a plant or a shadow, not paper: leave the picture alone
    if min(paper) < 110:
        return raw
    # each channel scaled so the paper reads white, then a white point a little
    # under it so an unevenly lit sheet (a vignette, a fold) goes white too
    luts = []
    for c in paper:
        scale = 255.0 / max(1, c) * (255.0 / WHITE_POINT)
        luts.extend(min(255, round(v * scale)) for v in range(256))
    out = io.BytesIO()
    im.point(luts).save(out, "PNG", optimize=True)
    return out.getvalue()


def flat_variant(key: str, path: Any) -> str:
    """Make ``<key>__flat.png`` beside a kept painting once, and name the
    variant for ``art.url``; '' (the painting itself) when it cannot be made."""
    if path is None:
        return ""
    try:
        flat = path.with_name(f"{key}__flat.png")
        if not flat.exists():
            data = flatten(path.read_bytes())
            tmp = flat.with_name(flat.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(flat)
        return "flat"
    except OSError:
        return ""


def _art_error(why: str) -> Exception:
    return artwork.ArtworkError(why) if artwork is not None else RuntimeError(why)


def make(job: Any) -> tuple[bytes, dict[str, Any]]:
    """One painting, on a worker thread: the photo from the payload as the
    reference, the prompt from the style, the picture from fal.ai through
    the collection's budget."""
    p = dict(job.payload)
    photo = str(p.get("photo") or "").strip()
    if not photo:
        raise _art_error("no openly licensed photo of the species to paint from")
    model = model_of(p.get("model"))
    prompt = prompt_for(p)
    raw = job.fal.generate(model, prompt, refs=[photo], aspect="3:4", retries=1)
    return raw, {
        "credit": credit_for(
            model, str(p.get("by") or ""), str(p.get("licence") or "")
        ),
        "style": style_id(p.get("style")),
        "name": str(p.get("common") or ""),
        "sci": str(p.get("sci") or ""),
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }


ART: Any = (
    artwork.Collection(
        "herbarium_sheet",
        "specimens",
        make=make,
        label="Herbarium Sheet",
        title="Pressing specimens",
        facet="style",
        facet_label=lambda s: style_of(s)[0],
    )
    if artwork is not None
    else _NoCollection("specimens")
)
