"""Agrégation (mode démo) : règle de sélection, seuils, build complet."""

from __future__ import annotations

import pytest

from lolbuilds.aggregation import (
    NotEnoughGames,
    SelectionParams,
    aggregate_build,
    select_best,
)
from conftest import PAGE_A, PAGE_B, PAGE_C, many

PARAMS = SelectionParams(min_pick_rate=0.05, min_games=10, min_champion_games=30)


def test_best_winrate_among_eligible():
    stats = {"A": [100, 50], "B": [30, 21], "C": [3, 3]}  # C : 100 % WR mais pick rate 2 %
    choice = select_best(stats, 133, min_pick_rate=0.05, min_games=10)
    assert choice.key == "B" and not choice.fallback


def test_pick_rate_threshold_excludes_rare_build():
    stats = {"A": [96, 48], "B": [4, 4]}  # B : 4 % < 5 %
    assert select_best(stats, 100, 0.05, 1).key == "A"


def test_min_games_threshold():
    stats = {"A": [40, 20], "B": [9, 9]}  # B : 18 % de pick mais 9 parties < 10
    assert select_best(stats, 49, 0.05, 10).key == "A"


def test_fallback_on_most_played_when_nothing_eligible():
    stats = {"A": [5, 1], "B": [3, 3]}
    choice = select_best(stats, 8, 0.05, min_games=20)
    assert choice.key == "A" and choice.fallback


def test_tie_on_winrate_prefers_more_games():
    stats = {"A": [20, 10], "B": [40, 20]}
    assert select_best(stats, 60, 0.05, 10).key == "B"


def test_empty_stats():
    assert select_best({}, 0, 0.05, 10) is None


# --------------------------------------------------------------------------- build complet

def test_aggregate_build_picks_higher_winrate_page(items):
    records = many(40, 20, page=PAGE_A) + many(15, 12, page=PAGE_B) + many(2, 2, page=PAGE_C)
    build = aggregate_build(records, champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=PARAMS)
    assert (build.primaryStyle, build.subStyle) == (PAGE_B[0], PAGE_B[1])
    assert build.perks[:6] == list(PAGE_B[2]) and len(build.perks) == 9
    assert build.sample_size == 57
    assert build.details["runes"]["fallback"] is False
    build.validate()


def test_aggregate_build_item_set(items):
    records = many(30, 18) + many(20, 8, core=(6655, 3089, 3157), boots=3158)
    build = aggregate_build(records, champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=PARAMS)
    blocks = {b["type"].split(" (")[0]: [int(i["id"]) for i in b["items"]] for b in build.itemSet["blocks"]}
    assert blocks["Core"] == [6655, 4645, 3089]
    assert blocks["Bottes"] == [3020]
    assert blocks["Départ"] == [1056, 2003]
    assert 3157 in blocks["Situationnel"] and 6655 not in blocks["Situationnel"]
    assert build.itemSet["title"].startswith("[Auto] Ahri Mid")
    assert build.itemSet["associatedChampions"] == [103]


def test_spell_order_follows_most_common_orientation(items):
    records = many(20, 10, spells=(4, 14)) + many(30, 15, spells=(14, 4))
    build = aggregate_build(records, champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=PARAMS)
    assert build.spells == [14, 4]


def test_not_enough_games(items):
    with pytest.raises(NotEnoughGames):
        aggregate_build(many(29, 15), champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=PARAMS)


def test_low_sample_falls_back_to_most_played(items):
    # Aucun build n'atteint min_games=50 : on prend le plus joué, et on le signale.
    params = SelectionParams(min_pick_rate=0.05, min_games=50, min_champion_games=30)
    records = many(20, 5, page=PAGE_A) + many(15, 15, page=PAGE_B)
    build = aggregate_build(records, champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=params)
    assert build.primaryStyle == PAGE_A[0]
    assert build.details["runes"]["fallback"] is True
