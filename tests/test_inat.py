"""The data shaping: the query for each window, the ranking, the photo and
credit picked off a record, the cache, and fetch() with no network."""

from __future__ import annotations

from datetime import date

from conftest import MELB

TODAY = date(2026, 10, 28)


def test_query_windows(server):
    INAT = server.INAT
    q = INAT.base_query((-37.81, 144.96), 10, "", "month", TODAY)
    assert q["month"] == "10" and "d1" not in q
    assert q["iconic_taxa"] == "Plantae" and q["quality_grade"] == "research"
    assert q["photo_license"] == "cc0,cc-by,cc-by-sa,cc-by-nc,cc-by-nc-sa"
    assert "nd" not in q["photo_license"] and q["radius"] == "10"
    q30 = INAT.base_query((-37.81, 144.96), 10, "", "30d", TODAY)
    assert q30["d1"] == "2026-09-28" and "month" not in q30
    q90 = INAT.base_query(None, 10, "someone", "90d", TODAY)
    assert (
        q90["d1"] == "2026-07-30"
        and q90["user_login"] == "someone"
        and "lat" not in q90
    )


def test_medium_and_licence_labels(server):
    INAT = server.INAT
    assert (
        INAT.medium("https://x/photos/5/square.jpg") == "https://x/photos/5/medium.jpg"
    )
    assert (
        INAT.medium("https://x/photos/5/medium.jpeg")
        == "https://x/photos/5/medium.jpeg"
    )
    assert INAT.licence_label("cc-by-nc-sa") == "CC BY-NC-SA"
    assert INAT.licence_label("cc0") == "CC0"
    assert INAT.licence_label("") == ""


def test_specimens_rank_and_credit(server, fake_inat):
    got, err = server.INAT.specimens((-37.81, 144.96), 10, "", "month", 2, TODAY)
    assert err is None
    rows = got["species"]
    assert [r["sci"] for r in rows] == ["Arctotheca calendula", "Plantago lanceolata"]
    cap = rows[0]
    # the licensed photo, not the first, at medium size; the observer's name over the login
    assert cap["photo"].endswith("/photos/2/medium.jpg")
    assert cap["by"] == "Audrey F" and cap["licence"] == "CC BY-NC"
    assert cap["latest"] == "2026-10-28" and cap["count"] == 60
    assert rows[1]["by"] == "pvesk"
    # two species asked for: one species_counts call and one observations call each
    assert len(fake_inat) == 3
    assert got["species_total"] == 3


def test_species_without_a_record_falls_back_to_the_taxon_photo(server, fake_inat):
    got, _ = server.INAT.specimens((-37.81, 144.96), 10, "", "month", 3, TODAY)
    clover = got["species"][2]
    assert clover["photo"].endswith("/photos/3/medium.jpg")
    assert clover["by"] == "Default Person" and clover["licence"] == "CC BY"
    assert clover["latest"] == ""


def test_fetch_shapes_the_sheet_and_caches(server, fake_inat, tmp_path):
    ctx = {"data_dir": str(tmp_path), "preview": False}
    d = server.fetch({**MELB, "count": "3"}, {}, ctx=ctx)
    assert "error" not in d
    assert d["head"] == "Melbourne" and d["where"] == "Collected within 10 km"
    assert d["title"] == "HERBARIUM" and d["layout"] == "mounted"
    assert len(d["species"]) == 3 and d["species"][0]["latest_text"] == "28 Oct"
    assert d["accession"].startswith(f"{date.today().year}.{date.today().month:02d}.")
    assert d["live_refresh_s"] == 0
    n = len(fake_inat)
    again = server.fetch({**MELB, "count": "3"}, {}, ctx=ctx)
    assert len(fake_inat) == n, "the second fetch came from the cache"
    assert again["species"] == d["species"]
    server.fetch({**MELB, "count": "3"}, {}, ctx={**ctx, "fresh": True})
    assert len(fake_inat) > n, "fresh bypasses the cache"


def test_single_plate_shows_one_and_user_mode_needs_a_name(server, fake_inat, tmp_path):
    ctx = {"data_dir": str(tmp_path)}
    d = server.fetch({**MELB, "layout": "plate", "count": "6"}, {}, ctx=ctx)
    assert len(d["species"]) == 1 and d["count"] == 1
    u = server.fetch({"source": "user", "user_login": ""}, {}, ctx=ctx)
    assert "username" in u["error"]
    u = server.fetch({"source": "user", "user_login": "@audrey"}, {}, ctx=ctx)
    assert u["where"] == "Collected by audrey" and u["head"] == "audrey"
    e = server.fetch({"source": "place"}, {}, ctx=ctx)
    assert "location" in e["error"]


def test_fetch_without_network_is_an_error_dict(server, offline, tmp_path):
    d = server.fetch(MELB, {}, ctx={"data_dir": str(tmp_path)})
    assert d["error"] == server.INAT.ERR_UNREACHABLE
    assert d["paper"] == "cream" and d["panel"] == "colour"


def test_fetch_without_network_uses_a_stale_cache(
    server, fake_inat, tmp_path, monkeypatch
):
    ctx = {"data_dir": str(tmp_path)}
    d = server.fetch(MELB, {}, ctx=ctx)
    assert "error" not in d
    monkeypatch.setattr(server, "CACHE_S", 0)
    import urllib.error
    import urllib.request

    def no_net(*a, **k):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(urllib.request, "urlopen", no_net)
    stale = server.fetch(MELB, {}, ctx=ctx)
    assert "error" not in stale and stale["species"] == d["species"]


def test_accession_is_stable_per_sheet(server):
    a = server.accession(TODAY, "sheet-a")
    assert a.startswith("2026.10.") and len(a) == len("2026.10.003")
    assert a == server.accession(TODAY, "sheet-a")
    assert a != server.accession(TODAY, "sheet-b")
