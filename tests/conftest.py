"""Fixtures communes : catalogues statiques et fabrique de participants (aucun réseau)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lolbuilds.aggregation import ParticipantRecord
from lolbuilds.ddragon import ChampionCatalog, ItemCatalog
from lolbuilds.models import Build

FIXTURES = Path(__file__).parent / "fixtures"

PAGE_A = (8100, 8300, (8112, 8139, 8138, 8106, 8345, 8347))  # Électrocution / Sorcellerie... page standard
PAGE_B = (8200, 8300, (8214, 8226, 8210, 8237, 8345, 8347))
PAGE_C = (8000, 8100, (8010, 9111, 9104, 8014, 8139, 8135))
SHARDS = (5008, 5008, 5011)


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def items() -> ItemCatalog:
    return ItemCatalog.from_ddragon(load_fixture("item_mini.json"))


@pytest.fixture
def champions() -> ChampionCatalog:
    return ChampionCatalog(by_key={103: "Ahri", 412: "Thresh", 62: "MonkeyKing"},
                           names={"Ahri": "Ahri", "Thresh": "Thresh", "MonkeyKing": "Wukong"})


def rec(
    win: bool,
    page: tuple = PAGE_A,
    shards: tuple = SHARDS,
    spells: tuple = (14, 4),
    core: tuple = (6655, 4645, 3089),
    boots: int = 3020,
    starter: tuple = (1056, 2003),
    with_timeline: bool = True,
    n: list = [0],
) -> ParticipantRecord:
    """Fabrique un participant Ahri mid ; `core` = ordre d'achat des items complétés."""
    n[0] += 1
    purchases = tuple((i, 1000) for i in starter) + tuple((i, 600_000 + k * 1000) for k, i in enumerate((boots, *core)))
    return ParticipantRecord(
        match_id=f"EUW1_{n[0]}",
        champion_id=103,
        position="middle",
        win=win,
        primary_style=page[0],
        sub_style=page[1],
        perks=(*page[2], *shards),
        spells=spells,
        items=(*core, boots, 0, 0, 3340)[:7],
        purchases=purchases if with_timeline else (),
    )


def many(count: int, wins: int, **kw) -> list[ParticipantRecord]:
    return [rec(i < wins, **kw) for i in range(count)]


def make_build(fetched_at: str = "2026-10-31", champion: str = "Ahri", role: str = "middle", **kw) -> Build:
    data = dict(
        champion=champion, champion_id=103, role=role, fetched_at=fetched_at, patch="15.21", name=f"{champion} Mid",
        primaryStyle=8100, subStyle=8300, perks=[8112, 8139, 8138, 8106, 8345, 8347, 5008, 5008, 5011],
        spells=[14, 4], itemSet={"title": "[Auto] Ahri Mid", "associatedChampions": [103], "blocks": []},
        sample_size=100, winrate=0.52,
    )
    data.update(kw)
    return Build(**data)
