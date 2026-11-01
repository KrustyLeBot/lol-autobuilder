"""Cache : fraîcheur, écriture atomique, fallback sur l'ancien build en cas d'erreur."""

from __future__ import annotations

import json
from datetime import date

import pytest

from lolbuilds.cache import BuildCache
from lolbuilds.models import Build, Target
from lolbuilds.prefetch import Outcome, refresh_all, refresh_one
from lolbuilds.sources import BuildSource, BuildSourceError, InsufficientDataError
from conftest import make_build

TODAY = date(2026, 10, 31)
AHRI = Target("Ahri", "middle")


class FakeSource(BuildSource):
    name = "fake"

    def __init__(self, error: Exception | None = None, build: Build | None = None) -> None:
        self.error, self.build = error, build
        self.calls: list[tuple[str, str]] = []
        self.prepared = 0

    def prepare(self, targets):
        self.prepared += 1

    def fetch_build(self, champion: str, role: str) -> Build:
        self.calls.append((champion, role))
        if self.error:
            raise self.error
        return self.build or make_build(fetched_at="", champion=champion, role=role, sample_size=999)


@pytest.fixture
def cache(tmp_path) -> BuildCache:
    return BuildCache(tmp_path)


def test_roundtrip_and_file_name(cache):
    path = cache.save(make_build())
    assert path.name == "Ahri_middle.json"
    loaded = cache.load("Ahri", "middle")
    assert loaded == make_build()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["fetched_at"] == "2026-10-31" and len(raw["perks"]) == 9


def test_freshness(cache):
    assert not cache.is_fresh("Ahri", "middle", TODAY)
    cache.save(make_build(fetched_at="2026-10-30"))
    assert not cache.is_fresh("Ahri", "middle", TODAY)
    cache.save(make_build(fetched_at="2026-10-31"))
    assert cache.is_fresh("Ahri", "middle", TODAY)


def test_corrupted_file_is_ignored(cache):
    cache.path_for("Ahri", "middle").write_text("{pas du json", encoding="utf-8")
    assert cache.load("Ahri", "middle") is None


def test_invalid_build_never_overwrites(cache):
    cache.save(make_build(fetched_at="2026-10-30"))
    with pytest.raises(ValueError):
        cache.save(make_build(perks=[1, 2, 3]))
    assert cache.load("Ahri", "middle").fetched_at == "2026-10-30"


def test_fresh_cache_skips_source(cache):
    cache.save(make_build(fetched_at=TODAY.isoformat()))
    source = FakeSource()
    assert refresh_one(cache, source, AHRI, TODAY) is Outcome.FRESH
    assert source.calls == []


def test_force_refetches(cache):
    cache.save(make_build(fetched_at=TODAY.isoformat()))
    source = FakeSource()
    assert refresh_one(cache, source, AHRI, TODAY, force=True) is Outcome.UPDATED
    assert source.calls == [("Ahri", "middle")]


def test_stale_cache_is_updated(cache):
    cache.save(make_build(fetched_at="2026-10-30", sample_size=1))
    assert refresh_one(cache, FakeSource(), AHRI, TODAY) is Outcome.UPDATED
    new = cache.load("Ahri", "middle")
    assert new.fetched_at == "2026-10-31" and new.sample_size == 999


@pytest.mark.parametrize("error", [BuildSourceError("API down"), InsufficientDataError("12 parties")])
def test_error_keeps_old_cache(cache, error):
    cache.save(make_build(fetched_at="2026-10-30", sample_size=42))
    before = cache.path_for("Ahri", "middle").read_bytes()
    assert refresh_one(cache, FakeSource(error=error), AHRI, TODAY) is Outcome.KEPT_OLD
    assert cache.path_for("Ahri", "middle").read_bytes() == before


def test_error_without_cache(cache):
    assert refresh_one(cache, FakeSource(error=BuildSourceError("x")), AHRI, TODAY) is Outcome.MISSING
    assert not cache.path_for("Ahri", "middle").exists()


def test_invalid_build_from_source_keeps_old(cache):
    cache.save(make_build(fetched_at="2026-10-30"))
    source = FakeSource(build=make_build(fetched_at="", spells=[4]))
    assert refresh_one(cache, source, AHRI, TODAY) is Outcome.KEPT_OLD


def test_refresh_all_prepares_only_when_needed(cache):
    cache.save(make_build(fetched_at=TODAY.isoformat()))
    source = FakeSource()
    refresh_all(cache, source, [AHRI], TODAY)
    assert source.prepared == 0

    thresh = Target("Thresh", "utility")
    results = refresh_all(cache, source, [AHRI, thresh], TODAY)
    assert source.prepared == 1
    assert results == {AHRI: Outcome.FRESH, thresh: Outcome.UPDATED}


def test_builds_for_champion_sorted_by_sample(cache):
    cache.save(make_build(role="middle", sample_size=10))
    cache.save(make_build(role="utility", sample_size=500))
    assert [b.role for b in cache.builds_for_champion("Ahri")] == ["utility", "middle"]
