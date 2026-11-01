"""Source OP.GG : format de réponse, conversion en build, cibles, client MCP (aucun réseau)."""

from __future__ import annotations

import json

import httpx
import pytest

from lolbuilds.config import OpggSettings
from lolbuilds.ddragon import ChampionCatalog, ItemCatalog, StaticData
from lolbuilds.models import Target
from lolbuilds.sources import BuildSourceError, InsufficientDataError
from lolbuilds.sources.opgg import (
    OpggClient,
    OpggSource,
    build_from_analysis,
    lane_roles,
    opgg_name,
    parse_toon,
)
from conftest import FIXTURES


def text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def static() -> StaticData:
    champs = ChampionCatalog(
        by_key={105: "Fizz", 103: "Ahri", 31: "Chogath", 62: "MonkeyKing", 20: "Nunu"},
        names={"Fizz": "Fizz", "Ahri": "Ahri", "Chogath": "Cho'Gath", "MonkeyKing": "Wukong", "Nunu": "Nunu & Willump"},
    )
    return StaticData(version="16.21.1", champions=champs, items=ItemCatalog())


def fizz():
    return parse_toon(text("opgg_fizz_mid.txt"))


# --------------------------------------------------------------------------- format

def test_parse_toon_maps_positional_fields():
    data = fizz()["data"]
    assert data["runes"]["primary_page_id"] == 8100
    assert data["runes"]["stat_mod_ids"] == [5008, 5008, 5001]
    assert data["boots"]["ids"] == [3020]
    assert isinstance(data["fourth_items"], list) and data["fourth_items"][0]["ids"]


def test_parse_toon_never_evaluates_code():
    with pytest.raises(BuildSourceError):
        parse_toon('class A: x\n\nA(__import__("os").getcwd())')


def test_opgg_name():
    assert opgg_name("Cho'Gath") == "CHO_GATH"
    assert opgg_name("Nunu & Willump") == "NUNU_WILLUMP"
    assert opgg_name("Dr. Mundo") == "DR_MUNDO"


# --------------------------------------------------------------------------- conversion

def test_build_from_analysis():
    b = build_from_analysis(fizz(), champion="Fizz", champion_id=105, role="middle", patch="16.21")
    assert b.perks == [8112, 8143, 8140, 8135, 8210, 8237, 5008, 5008, 5001]
    assert (b.primaryStyle, b.subStyle) == (8100, 8200)
    assert sorted(b.spells) == [4, 14]
    assert b.sample_size == 99280 and b.winrate == 0.51  # stats du rôle mid, pas tous rôles confondus
    assert b.itemSet["title"] == "[Auto] Fizz Mid 16.21"
    keys = [blk["key"] for blk in b.itemSet["blocks"]]
    assert keys == ["starter", "core", "boots", "situational", "consumables"]
    starter = b.itemSet["blocks"][0]["items"]
    assert {"id": "2003", "count": 2} in starter  # 2 potions regroupées
    core = {int(i["id"]) for i in b.itemSet["blocks"][1]["items"]}
    situ = [int(i["id"]) for i in b.itemSet["blocks"][3]["items"]]
    assert not core & set(situ) and 3020 not in situ
    assert len(b.variants) == 1 and b.variants[0]["details"]["skills"]
    assert b.spell_options[0]["most_played"]


def test_build_without_runes_is_insufficient():
    with pytest.raises(InsufficientDataError):
        build_from_analysis({"data": {}}, champion="Fizz", champion_id=105, role="middle", patch="16.21")


# --------------------------------------------------------------------------- cibles

def test_lane_roles_from_real_meta(static):
    roles = lane_roles(parse_toon(text("opgg_lane_meta.txt")), static.champions)
    assert roles["Fizz"]["middle"] > 0.5
    assert "Chogath" in roles and "MonkeyKing" in roles  # noms affichés -> ids Data Dragon


class FakeClient:
    def __init__(self, responses: dict[str, object]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []

    def call(self, tool: str, arguments: dict) -> object:
        self.calls.append((tool, arguments))
        return self.responses[tool]

    def close(self) -> None:
        pass


META = {"data": {"positions": {
    "mid": [{"champion": "Fizz", "role_rate": 0.9}, {"champion": "Cho'Gath", "role_rate": 0.05}],
    "top": [{"champion": "Fizz", "role_rate": 0.08}, {"champion": "Cho'Gath", "role_rate": 0.6}],
    "support": [{"champion": "Ahri", "role_rate": 0.02}],
}}}


def test_targets_keep_main_role_and_frequent_roles(static):
    src = OpggSource(static, OpggSettings(min_role_rate=0.1), FakeClient({"lol_list_lane_meta_champions": META}))
    assert src.targets() == [Target("Ahri", "utility"), Target("Chogath", "top"), Target("Fizz", "middle")]
    assert src.main_role("Chogath") == "top"
    assert len(src.client.calls) == 1  # méta mise en mémoire


def test_fetch_build_arguments(static):
    client = FakeClient({"lol_get_champion_analysis": fizz()})
    src = OpggSource(static, OpggSettings(tier="master_plus"), client)
    b = src.fetch_build("Fizz", "middle")
    tool, args = client.calls[0]
    assert (args["champion"], args["position"], args["tier"], args["game_mode"]) == ("FIZZ", "mid", "master_plus", "ranked")
    assert b.source == "opgg" and b.patch == "16.21"


def test_unknown_tier_rejected():
    with pytest.raises(ValueError):
        OpggSettings(tier="platine")


# --------------------------------------------------------------------------- client MCP

def mcp_transport(fail_first: int = 0):
    state = {"calls": 0, "fail": fail_first}

    def handler(request: httpx.Request) -> httpx.Response:
        msg = json.loads(request.content)
        if msg["method"] == "initialize":
            return httpx.Response(200, headers={"mcp-session-id": "s1"}, json={"jsonrpc": "2.0", "id": msg["id"], "result": {}})
        if msg["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert request.headers["mcp-session-id"] == "s1"
        state["calls"] += 1
        if state["fail"]:
            state["fail"] -= 1
            return httpx.Response(429)
        body = 'class R: a,b\n\nR(1,[2,3])'
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text="event: message\ndata: " + json.dumps(
                                  {"jsonrpc": "2.0", "id": msg["id"], "result": {"content": [{"type": "text", "text": body}]}}))

    return httpx.MockTransport(handler), state


def test_client_session_and_sse(monkeypatch):
    transport, _ = mcp_transport()
    client = OpggClient(interval=0, http=httpx.Client(transport=transport))
    assert client.call("x", {}) == {"a": 1, "b": [2, 3]}


def test_client_retries_on_429(monkeypatch):
    monkeypatch.setattr("lolbuilds.sources.opgg.time.sleep", lambda _s: None)
    transport, state = mcp_transport(fail_first=2)
    client = OpggClient(interval=0, http=httpx.Client(transport=transport))
    assert client.call("x", {})["a"] == 1 and state["calls"] == 3


def test_client_gives_up(monkeypatch):
    monkeypatch.setattr("lolbuilds.sources.opgg.time.sleep", lambda _s: None)
    transport, _ = mcp_transport(fail_first=10)
    client = OpggClient(interval=0, http=httpx.Client(transport=transport))
    with pytest.raises(BuildSourceError):
        client.call("x", {}, retries=2)


def test_aram_build_from_analysis():
    b = build_from_analysis(fizz(), champion="Fizz", champion_id=105, role="aram", patch="16.21")
    assert b.role == "aram" and b.name == "Fizz ARAM"
    assert b.itemSet["title"] == "[Auto] Fizz ARAM 16.21"
    assert b.itemSet["associatedMaps"] == [12]  # Abîme hurlant
    assert b.variants[0]["tags"] == ["Build ARAM"]
    classic = build_from_analysis(fizz(), champion="Fizz", champion_id=105, role="middle", patch="16.21")
    assert classic.itemSet["associatedMaps"] == [11]


def test_aram_targets_follow_the_option():
    from lolbuilds.config import OpggSettings

    static = StaticData(version="16.21.1", champions=ChampionCatalog(by_key={}, names={}), items=ItemCatalog())
    on = OpggSource(static, OpggSettings(), client=None)
    assert on.aram_targets(["Fizz", "Ahri", "Fizz"]) == [Target("Ahri", "aram"), Target("Fizz", "aram")]
    off = OpggSource(static, OpggSettings(aram=False), client=None)
    assert off.aram_targets(["Fizz"]) == []
