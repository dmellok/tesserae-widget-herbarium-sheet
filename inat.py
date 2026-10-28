"""iNaturalist for the Herbarium Sheet: the plants recorded in flower or fruit
near a place (or by one user) in a window, ranked by how often, each with its
best openly licensed photo, the photographer and licence for the credit, and
the date of the latest record. Loaded by server.py by path; urllib only.

Two calls make a sheet: ``observations/species_counts`` ranks the species,
then one small ``observations`` call per chosen species finds its newest
record with a licensed photo. A sheet shows at most six species, so that is
at most seven calls, and the result is cached for six hours by server.py."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from typing import Any

USER_AGENT = "tesserae/herbarium_sheet/0.1.0 (+https://github.com/dmellok/tesserae-widget-herbarium-sheet)"
TIMEOUT_S = 15
API = "https://api.inaturalist.org/v1"
SPECIES_COUNTS = f"{API}/observations/species_counts"
OBSERVATIONS = f"{API}/observations"
# No NoDerivatives licences: an AI painting made from a photo is a derivative
# work, which CC BY-ND and CC BY-NC-ND forbid, so those photos are left out.
LICENSED = "cc0,cc-by,cc-by-sa,cc-by-nc,cc-by-nc-sa"
WINDOWS = ("month", "30d", "90d")
MAX_SPECIES = 6
SPECIES_PER_PAGE = 20

ERR_UNREACHABLE = (
    "iNaturalist could not be reached. The sheet will try again at the next refresh."
)
ERR_BUSY = "iNaturalist answered {err}. The sheet will try again at the next refresh."
ERR_SHAPE = "iNaturalist's answer was not in the expected shape."


def get_json(url: str) -> tuple[Any | None, str | None]:
    """(parsed JSON, None) or (None, why). Never raises."""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = resp.read(4_000_000)
    except urllib.error.HTTPError as err:
        return None, f"HTTP {err.code}"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return None, "unreachable"
    try:
        return json.loads(body.decode("utf-8")), None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, "not json"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")[:60] or "x"


def medium(url: str) -> str:
    """iNaturalist hands out the 75 px square; the same path at /medium is 500 px."""
    return re.sub(r"/(square|small|thumb)\.", "/medium.", str(url or ""))


def licence_label(code: str) -> str:
    """'cc-by-nc' -> 'CC BY-NC'; CC0 stays 'CC0'."""
    code = str(code or "").strip().lower()
    if not code:
        return ""
    if code == "cc0":
        return "CC0"
    return code.upper().replace("CC-", "CC ", 1)


def base_query(
    place: tuple[float, float] | None,
    radius_km: int,
    login: str,
    window: str,
    today: date,
) -> dict[str, str]:
    """The parameters every call shares: research-grade plants with a licensed
    photo, near the place or by the user, in the window. 'month' is the
    current calendar month in any year (the seasonal view); '30d' and '90d'
    count back from to-day."""
    q = {
        "iconic_taxa": "Plantae",
        "quality_grade": "research",
        "photos": "true",
        "photo_license": LICENSED,
        "locale": "en",
    }
    if place is not None:
        q["lat"] = f"{place[0]:.4f}"
        q["lng"] = f"{place[1]:.4f}"
        q["radius"] = str(int(radius_km))
    if login:
        q["user_login"] = login
    if window == "30d":
        q["d1"] = (today - timedelta(days=30)).isoformat()
    elif window == "90d":
        q["d1"] = (today - timedelta(days=90)).isoformat()
    else:
        q["month"] = str(today.month)
    return q


def pick_photo(obs: dict[str, Any]) -> dict[str, Any] | None:
    """The first photo on an observation that carries a licence; the filter
    only promises one of them does."""
    for p in obs.get("photos") or []:
        if isinstance(p, dict) and p.get("url") and p.get("license_code"):
            return p
    return None


def photographer(obs: dict[str, Any], photo: dict[str, Any] | None) -> str:
    """The observer's display name, else their login, else what the photo's
    attribution line says."""
    user = obs.get("user") or {}
    who = str(user.get("name") or user.get("login") or "").strip()
    if who:
        return who
    attr = str((photo or {}).get("attribution") or "")
    m = re.match(r"\(c\)\s*([^,]+)", attr)
    return m.group(1).strip() if m else ""


def specimen_from(
    taxon: dict[str, Any], count: int, obs: dict[str, Any] | None
) -> dict[str, Any]:
    """One species row from its species_counts taxon and its newest record."""
    sci = str(taxon.get("name") or "").strip()
    common = str(taxon.get("preferred_common_name") or "").strip()
    photo = pick_photo(obs) if obs else None
    row = {
        "sci": sci,
        "common": common or sci,
        "count": int(count or 0),
        "taxon_id": int(taxon.get("id") or 0),
        "latest": str((obs or {}).get("observed_on") or ""),
        "photo": medium(photo["url"]) if photo else "",
        "by": photographer(obs, photo) if obs else "",
        "licence": licence_label((photo or {}).get("license_code") or ""),
    }
    if not row["photo"]:
        # the taxon's default photo, only when it is openly licensed too
        dp = taxon.get("default_photo") or {}
        if dp.get("license_code") and (dp.get("medium_url") or dp.get("url")):
            row["photo"] = str(dp.get("medium_url") or medium(dp.get("url")))
            row["licence"] = licence_label(dp.get("license_code"))
            m = re.match(r"\(c\)\s*([^,]+)", str(dp.get("attribution") or ""))
            row["by"] = m.group(1).strip() if m else ""
    return row


def specimens(
    place: tuple[float, float] | None,
    radius_km: int,
    login: str,
    window: str,
    count: int,
    today: date,
) -> tuple[dict[str, Any] | None, str | None]:
    """The sheet's species: ({species: [...], species_total: n}, None) or
    (None, a friendly sentence). Never raises."""
    q = base_query(place, radius_km, login, window, today)
    sq = urllib.parse.urlencode({**q, "per_page": str(SPECIES_PER_PAGE)})
    got, err = get_json(f"{SPECIES_COUNTS}?{sq}")
    if err == "unreachable":
        return None, ERR_UNREACHABLE
    if err:
        return None, ERR_BUSY.format(err=err)
    if not isinstance(got, dict) or not isinstance(got.get("results"), list):
        return None, ERR_SHAPE
    ranked = sorted(
        (
            r
            for r in got["results"]
            if isinstance(r, dict) and isinstance(r.get("taxon"), dict)
        ),
        key=lambda r: (-int(r.get("count") or 0), str(r["taxon"].get("name") or "")),
    )
    n = max(1, min(MAX_SPECIES, int(count or 1)))
    rows: list[dict[str, Any]] = []
    for r in ranked[:n]:
        taxon = r["taxon"]
        oq = urllib.parse.urlencode(
            {
                **q,
                "taxon_id": str(taxon.get("id") or ""),
                "order_by": "observed_on",
                "order": "desc",
                "per_page": "3",
            }
        )
        obs, oerr = get_json(f"{OBSERVATIONS}?{oq}")
        newest = None
        if not oerr and isinstance(obs, dict) and isinstance(obs.get("results"), list):
            for o in obs["results"]:
                if isinstance(o, dict) and pick_photo(o):
                    newest = o
                    break
            if (
                newest is None
                and obs["results"]
                and isinstance(obs["results"][0], dict)
            ):
                newest = obs["results"][0]
        rows.append(specimen_from(taxon, int(r.get("count") or 0), newest))
    return {
        "species": rows,
        "species_total": int(got.get("total_results") or len(ranked)),
    }, None
