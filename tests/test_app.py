"""Interface : variantes de build et contrôleur (session -> build affiché -> application), sans client."""

from __future__ import annotations

import asyncio

import pytest

from lolbuilds.aggregation import SelectionParams, aggregate_build
from lolbuilds.app import server
from lolbuilds.app.server import Controller
from lolbuilds.cache import BuildCache
from lolbuilds.config import Config, OpggSettings
from conftest import PAGE_A, PAGE_B, PAGE_C, many
from test_applier import FakeLcu, session

PARAMS = SelectionParams(min_pick_rate=0.05, min_games=10, min_champion_games=30, max_variants=3)


def ahri_build(items):
    records = (many(40, 20, page=PAGE_A) + many(20, 14, page=PAGE_B, spells=(4, 12))
               + many(30, 16, page=PAGE_C, core=(6655, 3089, 3157)))
    build = aggregate_build(records, champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=PARAMS)
    build.fetched_at = "2026-10-31"
    return build


def test_variants_sorted_by_winrate_with_most_played(items):
    b = ahri_build(items)
    assert [(v["primaryStyle"], v["games"]) for v in b.variants] == [(8200, 20), (8000, 30), (8100, 40)]
    assert b.variants[0]["tags"] == ["Meilleur winrate"]
    assert "Le plus joué" in b.variants[2]["tags"]
    assert (b.primaryStyle, b.perks) == (b.variants[0]["primaryStyle"], b.variants[0]["perks"])


def test_variant_specific_items_and_spells(items):
    b = ahri_build(items)
    best = b.variant(0)
    assert best.spells == [4, 12]
    third = b.variant(1)  # page C : core différent
    core = next(bl for bl in third.itemSet["blocks"] if bl["key"] == "core")
    assert [int(i["id"]) for i in core["items"]] == [6655, 3089, 3157]
    third.validate()


def test_most_played_kept_when_out_of_top(items):
    params = SelectionParams(0.05, 10, 30, max_variants=1)
    records = many(40, 18, page=PAGE_A) + many(20, 15, page=PAGE_B)
    b = aggregate_build(records, champion="Ahri", champion_id=103, role="middle", patch="15.21", items=items, params=params)
    assert len(b.variants) == 1 and b.variants[0]["primaryStyle"] == PAGE_A[0]


def test_spell_options(items):
    b = ahri_build(items)
    pairs = [sorted(o["spells"]) for o in b.spell_options]
    assert sorted([4, 12]) in pairs and sorted([4, 14]) in pairs
    assert any(o["most_played"] for o in b.spell_options)


@pytest.fixture
def ctrl(tmp_path, items, champions, monkeypatch):
    monkeypatch.setattr(server, "APPLY_DEBOUNCE", 0)
    BuildCache(tmp_path).save(ahri_build(items))
    c = Controller(Config(cache_dir=tmp_path, opgg=OpggSettings(live=False)))  # mode 100 % cache
    c.champions = champions
    return c


def test_session_loads_build_and_auto_applies(ctrl):
    lcu = FakeLcu()
    ctrl.lcu = lcu

    async def scenario():
        await ctrl.on_session(session())
        await asyncio.sleep(0.01)
        await ctrl._apply_task

    asyncio.run(scenario())
    assert ctrl.state["current"]["champion"] == "Ahri" and ctrl.state["current"]["locked"]
    assert ctrl.state["applied"]["variant"] == 0 and ctrl.state["applied"]["auto"]
    assert all(ctrl.state["applied"]["steps"].values())
    post = next(b for m, p, b in lcu.calls if m == "POST")
    assert post["primaryStyleId"] == 8200


def test_manual_choice_is_remembered(ctrl):
    ctrl.lcu = FakeLcu()
    ctrl.prefs.data["autoApply"] = False

    async def scenario():
        await ctrl.on_session(session())
        return await ctrl.apply(2)

    result = asyncio.run(scenario())
    assert result["ok"] and ctrl.state["applied"]["variant"] == 2
    assert ctrl.prefs.data["preferred"]["Ahri_middle"] == 2
    # Session suivante : la variante préférée est présélectionnée.
    asyncio.run(ctrl.on_session(None))
    asyncio.run(ctrl.on_session(session()))
    assert ctrl.state["selection"]["variant"] == 2


def test_apply_refused_outside_champ_select(ctrl):
    ctrl.lcu = FakeLcu()
    ctrl.load_build(103, "middle")
    result = asyncio.run(ctrl.apply(0))
    assert not result["ok"] and ctrl.lcu.calls == []


def test_hover_shows_build_without_applying(ctrl):
    lcu = FakeLcu()
    ctrl.lcu = lcu
    hover = session(champion_id=0)
    hover["myTeam"][1]["championPickIntent"] = 103
    asyncio.run(ctrl.on_session(hover))
    assert ctrl.state["current"]["champion"] == "Ahri" and not ctrl.state["current"]["locked"]
    assert lcu.calls == []


def test_demo_cycle_has_my_ban_and_pick_turns(ctrl):
    from lolbuilds.app.demo import DEMO_STEPS, demo_session, demo_step

    seen = {}
    t = 0.0
    while t < sum(d for _, d in DEMO_STEPS):
        step, ends = demo_step(1000 + t, 1000)
        summary = ctrl._summarize_session(demo_session(103, ends, step))
        seen[step] = (summary["turn"], summary["banPending"])
        t += 1
    assert seen["ban"] == ({"id": 3, "type": "ban"}, True)
    assert seen["wait"] == (None, False)
    assert seen["pick"] == ({"id": 13, "type": "pick"}, False)
    assert seen["locked"] == (None, False)


def test_prefs_update_validates_and_merges(tmp_path):
    from lolbuilds.app.server import SOUND_EVENTS, Prefs

    p = Prefs(tmp_path / "ui_prefs.json", "F")
    p.update({"theme": "noxus", "volume": 3, "alertFocus": 0, "sounds": {"myBan": "cloche", "myPick": "boum", "x": "bip"}})
    p.update({"theme": "bilgewater", "flashKey": "Q"})  # inconnus : ignorés
    assert p.data["theme"] == "noxus" and p.data["volume"] == 1.0 and p.data["alertFocus"] is False
    assert p.data["sounds"]["myBan"] == "cloche" and p.data["sounds"]["myPick"] == SOUND_EVENTS["myPick"]
    assert "x" not in p.data["sounds"] and p.data["flashKey"] == "F"
    p.save()
    again = Prefs(tmp_path / "ui_prefs.json", "F")
    assert again.data["sounds"]["myBan"] == "cloche" and set(again.data["sounds"]) == set(SOUND_EVENTS)


def test_session_stage(ctrl):
    from lolbuilds.app.demo import demo_session

    assert ctrl._summarize_session(demo_session(103, 0, "ban"))["stage"] == "ban"
    assert ctrl._summarize_session(demo_session(103, 0, "pick"))["stage"] == "pick"
    assert ctrl._summarize_session(demo_session(103, 0, "locked"))["stage"] == "ban_pick"
