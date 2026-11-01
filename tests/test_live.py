"""Récupération au moment du pick : adversaire de lane, cache d'une journée, matchups, bons picks."""

from __future__ import annotations

import asyncio
import json
from datetime import date

import pytest

from lolbuilds.app import server
from lolbuilds.app.server import Controller, select_counter_picks
from lolbuilds.cache import BuildCache
from lolbuilds.config import Config
from lolbuilds.ddragon import ChampionCatalog, ItemCatalog, StaticData
from lolbuilds.live import LiveBuilds, guess_lanes
from lolbuilds.sources import BuildSourceError
from lolbuilds.sources.opgg import build_from_analysis, counters_from_guide, matchup_variants, parse_toon
from conftest import FIXTURES, make_build
from test_applier import FakeLcu, session

ROLES = {
    "Syndra": {"middle": 0.9},
    "Thresh": {"utility": 0.95},
    "Pantheon": {"top": 0.4, "utility": 0.3, "middle": 0.2},
    "Ahri": {"middle": 0.95},
}


# Syndra contre chaque adversaire (extrait de `data.counters` du guide de matchup).
COUNTER_GUIDE = {"data": {"counters": [
    {"champion_id": 55, "champion_name": "Katarina", "play": 4092, "win": 1824},  # Katarina gagne 55,4 %
    {"champion_id": 105, "champion_name": "Fizz", "play": 4392, "win": 1985},
    {"champion_id": 103, "champion_name": "Ahri", "play": 7994, "win": 4028},  # Ahri perd (49,6 %)
    {"champion_id": 161, "champion_name": "Vel'Koz", "play": 120, "win": 40},  # trop peu de parties
]}}


def guide():
    return json.loads((FIXTURES / "opgg_matchup_ahri_syndra.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- adversaire

def test_guess_lanes_maximizes_role_rates():
    lanes = guess_lanes(["Syndra", "Thresh", "Pantheon"], ROLES)
    assert lanes == {"Syndra": "middle", "Thresh": "utility", "Pantheon": "top"}


def test_guess_lanes_flex_pick_takes_free_role():
    # Syndra absente : Pantheon peut être mid, mais top reste son meilleur rôle.
    assert guess_lanes(["Thresh", "Pantheon"], ROLES)["Pantheon"] == "top"
    assert guess_lanes(["Inconnu"], ROLES) == {}


# --------------------------------------------------------------------------- matchup

def test_matchup_variants_from_real_guide():
    variants = matchup_variants(guide(), opponent="Syndra")
    assert len(variants) == 2
    assert variants[0]["winrate"] >= variants[1]["winrate"]
    assert all(len(v["perks"]) == 9 and v["tags"][0] == "Contre Syndra" for v in variants)
    keystones = {v["perks"][0] for v in variants}
    assert keystones == {8112, 8992}  # pages ne différant que par les shards regroupées
    assert "Le plus joué" in variants[0]["tags"]


def test_matchup_without_runes_gives_nothing():
    assert matchup_variants({"data": {}}, opponent="Syndra") == []


# --------------------------------------------------------------------------- cache d'une journée

class FakeSource:
    name = "opgg"

    def __init__(self, fail: bool = False) -> None:
        champs = ChampionCatalog(by_key={103: "Ahri", 134: "Syndra", 412: "Thresh", 80: "Pantheon"},
                                 names={"Ahri": "Ahri", "Syndra": "Syndra", "Thresh": "Thresh", "Pantheon": "Pantheon"})
        self.static = StaticData(version="16.21.1", champions=champs, items=ItemCatalog())
        self._roles = None
        self.fail = fail
        self.calls: list[str] = []

    def roles(self):
        self.calls.append("roles")
        return ROLES

    def fetch_build(self, champion, role):
        self.calls.append(f"build {champion} {role}")
        if self.fail:
            raise BuildSourceError("hors ligne")
        analysis = parse_toon((FIXTURES / "opgg_fizz_mid.txt").read_text(encoding="utf-8"))
        return build_from_analysis(analysis, champion=champion, champion_id=103, role=role, patch="16.21")

    def fetch_matchup(self, champion, role, opponent):
        self.calls.append(f"matchup {champion} {opponent}")
        if self.fail:
            raise BuildSourceError("hors ligne")
        return matchup_variants(guide(), opponent=opponent)

    def fetch_counters(self, enemy, role):
        self.calls.append(f"counters {enemy} {role}")
        return counters_from_guide(COUNTER_GUIDE)

    def fetch_tier_list(self, role):
        self.calls.append(f"tiers {role}")
        return [{"championId": cid, "tier": 1, "rank": i, "winrate": 0.52, "pickRate": 0.1, "banRate": 0.2, "games": 9000}
                for i, cid in enumerate([103, 134, 55, 105, 80, 412, 161, 245])]

    def close(self):
        pass


@pytest.fixture
def live(tmp_path):
    cfg = Config(cache_dir=tmp_path)
    return LiveBuilds(cfg, BuildCache(tmp_path), source=FakeSource())


def test_global_build_fetched_once_per_day(live):
    b = live.global_build("Ahri", "middle")
    assert b and b.fetched_at == date.today().isoformat()
    live.global_build("Ahri", "middle")
    assert live.source.calls.count("build Ahri middle") == 1


def test_global_build_keeps_old_cache_when_offline(tmp_path):
    cache = BuildCache(tmp_path)
    cache.save(make_build(fetched_at="2026-01-01"))
    live = LiveBuilds(Config(cache_dir=tmp_path), cache, source=FakeSource(fail=True))
    assert live.global_build("Ahri", "middle").fetched_at == "2026-01-01"


def test_matchup_cached_for_the_day(live, tmp_path):
    assert len(live.matchup("Ahri", "middle", "Syndra")) == 2
    assert len(live.matchup("Ahri", "middle", "Syndra")) == 2
    assert live.source.calls.count("matchup Ahri Syndra") == 1
    path = tmp_path / "matchups" / "Ahri_middle_vs_Syndra.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["date"] = "2026-01-01"  # le lendemain : nouvel appel
    path.write_text(json.dumps(data), encoding="utf-8")
    live.matchup("Ahri", "middle", "Syndra")
    assert live.source.calls.count("matchup Ahri Syndra") == 2


def test_roles_cached_for_the_day(tmp_path):
    first = LiveBuilds(Config(cache_dir=tmp_path), BuildCache(tmp_path), source=FakeSource())
    assert first.role_for("Pantheon", "") == "top"
    second = LiveBuilds(Config(cache_dir=tmp_path), BuildCache(tmp_path), source=FakeSource())
    assert second.guess_opponent(["Syndra", "Thresh"], "middle") == "Syndra"
    assert "roles" not in second.source.calls  # relu depuis opgg/lanes.json


# --------------------------------------------------------------------------- contrôleur

@pytest.fixture
def ctrl(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "APPLY_DEBOUNCE", 0)
    c = Controller(Config(cache_dir=tmp_path))
    c.live = LiveBuilds(c.cfg, c.cache, source=FakeSource())
    c.champions = c.live.source.static.champions
    c.lcu = FakeLcu()
    return c


def ahri_vs(enemies):
    s = session()
    s["theirTeam"] = [{"cellId": 6 + i, "championId": cid} for i, cid in enumerate(enemies)]
    return s


def run(ctrl, sess):
    async def scenario():
        await ctrl.on_session(sess)
        await ctrl._live_refresh()
        if ctrl._apply_task:
            await ctrl._apply_task

    asyncio.run(scenario())


def test_pick_fetches_build_and_matchup_then_auto_applies(ctrl):
    run(ctrl, ahri_vs([134, 412]))
    cur = ctrl.state["current"]
    assert cur["opponent"] == {"championId": 134, "guessed": True, "status": "ok"}
    variants = cur["build"]["variants"]
    assert [v["tags"][0] for v in variants] == ["Contre Syndra", "Contre Syndra", "Recommandé OP.GG"]
    assert ctrl.state["applied"]["variant"] == 0 and ctrl.state["applied"]["auto"]
    post = next(b for m, p, b in ctrl.lcu.calls if m == "POST")
    assert post["selectedPerkIds"][0] == variants[0]["perks"][0]


def test_same_matchup_not_refetched(ctrl):
    run(ctrl, ahri_vs([134]))
    asyncio.run(ctrl._live_refresh())
    asyncio.run(ctrl._live_refresh())
    assert ctrl.live.source.calls.count("matchup Ahri Syndra") == 1
    assert ctrl.live.source.calls.count("build Ahri middle") == 1


def test_manual_opponent_overrides_guess(ctrl):
    run(ctrl, ahri_vs([134, 80]))
    ctrl._opponent_override = 80
    asyncio.run(ctrl._live_refresh())
    assert ctrl.state["current"]["opponent"]["championId"] == 80
    assert not ctrl.state["current"]["opponent"]["guessed"]
    assert "matchup Ahri Pantheon" in ctrl.live.source.calls


def test_manual_choice_stops_auto_apply(ctrl):
    ctrl.prefs.data["autoApply"] = True
    run(ctrl, ahri_vs([]))  # pas encore d'adversaire : build global appliqué
    asyncio.run(ctrl.apply(0))  # choix manuel
    calls = len(ctrl.lcu.calls)
    run(ctrl, ahri_vs([134]))  # l'adversaire arrive ensuite
    assert ctrl.state["current"]["build"]["variants"][0]["tags"][0] == "Contre Syndra"
    assert len(ctrl.lcu.calls) == calls  # rien réappliqué derrière l'utilisateur


# --------------------------------------------------------------------------- bons picks

def test_counters_from_guide_are_from_the_picker_side():
    counters = counters_from_guide(COUNTER_GUIDE)
    assert counters[0]["championId"] == 161 and counters[0]["winrate"] == round(1 - 40 / 120, 4)
    kata = next(c for c in counters if c["championId"] == 55)
    assert kata["winrate"] == round(1 - 1824 / 4092, 4) and kata["games"] == 4092


def test_select_counter_picks_filters_and_marks_mains():
    counters = counters_from_guide(COUNTER_GUIDE)
    picks = select_counter_picks(counters, unavailable=set(), owned=None, mastery={105: 90000})
    assert [p["championId"] for p in picks] == [55, 105]  # Vel'Koz : échantillon ; Ahri : < 50 %
    assert picks[1]["main"] and not picks[0]["main"]
    assert [p["championId"] for p in select_counter_picks(counters, {55}, None, {})] == [105]  # bannie / prise
    assert select_counter_picks(counters, set(), owned={103}, mastery={}) == []  # non possédés


def test_counters_cached_for_the_day(live):
    live.counters("Syndra", "middle")
    live.counters("Syndra", "middle")
    assert live.source.calls.count("counters Syndra middle") == 1


class PoolLcu(FakeLcu):
    async def request(self, method, path, body=None):
        if path == "/lol-champions/v1/owned-champions-minimal":
            return 200, [{"id": 105, "active": True, "ownership": {"owned": True}},
                         {"id": 55, "active": True, "ownership": {"owned": False}, "freeToPlay": False}]
        if path == "/lol-champion-mastery/v1/local-player/champion-mastery":
            return 200, [{"championId": 105, "championPoints": 120000}]
        return await super().request(method, path, body)


def before_pick(enemies, bans=()):
    s = ahri_vs(enemies)
    s["myTeam"][1]["championId"] = 0
    s["actions"] = [[{"type": "ban", "completed": True, "championId": b, "isAllyAction": True} for b in bans]]
    return s


def test_counter_picks_before_pick_use_owned_champions(ctrl):
    ctrl.lcu = PoolLcu()
    run(ctrl, before_pick([134, 412]))
    cp = ctrl.state["counterPicks"]
    assert cp["enemyId"] == 134 and cp["guessed"] and cp["status"] == "ok"
    assert [p["championId"] for p in cp["picks"]] == [105]  # Katarina non possédée
    assert cp["picks"][0]["main"]
    assert ctrl.state["current"] is None  # rien de choisi : pas de build affiché


def test_counter_picks_skip_banned_and_hidden_once_locked(ctrl):
    run(ctrl, before_pick([134], bans=[55]))
    assert [p["championId"] for p in ctrl.state["counterPicks"]["picks"]] == [105]
    run(ctrl, ahri_vs([134]))  # Ahri verrouillée : plus de suggestions
    assert ctrl.state["counterPicks"] is None
    assert ctrl.live.source.calls.count("counters Syndra middle") == 1


# --------------------------------------------------------------------------- mon tour, bans suggérés

def ban_phase(intent=0, my_ban_done=False, in_progress=True, enemies=(), bans=(), phase="BAN_PICK"):
    s = before_pick(list(enemies), bans=bans)
    s["myTeam"][0].update(championId=0, championPickIntent=105)  # un allié veut Fizz : jamais suggéré en ban
    s["myTeam"][1]["championPickIntent"] = intent
    s["actions"].append([{"id": 11, "actorCellId": 2, "type": "ban", "championId": 0,
                          "completed": my_ban_done, "isInProgress": in_progress and not my_ban_done}])
    s["timer"] = {"phase": phase, "adjustedTimeLeftInPhase": 30000, "totalTimeInPhase": 30000}
    return s


def test_my_turn_is_detected(ctrl):
    asyncio.run(ctrl.on_session(ban_phase()))
    assert ctrl.state["champSelect"]["turn"] == {"id": 11, "type": "ban"}
    assert ctrl.state["champSelect"]["banPending"] and ctrl.state["champSelect"]["stage"] == "ban"
    asyncio.run(ctrl.on_session(ban_phase(in_progress=False)))  # pas encore à moi
    assert ctrl.state["champSelect"]["turn"] is None and ctrl.state["champSelect"]["banPending"]


def test_prepick_is_not_a_ban_turn(ctrl):
    # Pendant le prépick, le client marque déjà le ban « en cours » : ce n'est pas encore mon tour.
    asyncio.run(ctrl.on_session(ban_phase(phase="PLANNING")))
    cs = ctrl.state["champSelect"]
    assert cs["turn"] is None and cs["stage"] == "planning"
    assert cs["banPending"]  # les bans suggérés peuvent déjà s'afficher pour préparer son ban
    asyncio.run(ctrl.on_session(ban_phase(phase="BAN_PICK")))  # la vraie phase de bans commence
    assert ctrl.state["champSelect"]["turn"] == {"id": 11, "type": "ban"}


def test_ban_suggestions_from_tier_list(ctrl):
    run(ctrl, ban_phase(bans=[134]))
    bs = ctrl.state["banSuggestions"]
    assert bs["mode"] == "meta" and bs["role"] == "middle"
    ids = [p["championId"] for p in bs["picks"]]
    assert 134 not in ids and 105 not in ids  # déjà bannie / voulue par un allié
    assert ids == [103, 55, 80, 412, 161, 245]


def test_ban_suggestions_threats_for_declared_champion(ctrl):
    run(ctrl, ban_phase(intent=134))  # je compte prendre Syndra
    bs = ctrl.state["banSuggestions"]
    assert bs["mode"] == "threats" and bs["championId"] == 134
    assert [p["championId"] for p in bs["picks"]] == [55]  # Fizz voulu par un allié, Vel'Koz : échantillon


def test_no_ban_suggestions_once_banned(ctrl):
    run(ctrl, ban_phase(my_ban_done=True))
    assert ctrl.state["banSuggestions"] is None
