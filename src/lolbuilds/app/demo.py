"""Mode démo : un faux champ select et des builds d'exemple, sans client ni clé API.

Les builds d'exemple sont générés à partir de parties fictives et écrits dans
`<cache>/demo/`, jamais dans le vrai cache. Les écritures LCU sont seulement loguées.
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from datetime import date
from typing import Any

from ..aggregation import ParticipantRecord, SelectionParams, aggregate_build
from ..cache import BuildCache
from .applier import DryRunLcu
from ..assets import AssetStore
from ..ddragon import DataDragon, StaticData

log = logging.getLogger(__name__)

# Champions de la démo : (id Data Dragon, rôle, styles de runes proposés, items core candidats)
DEMO_CHAMPIONS = [
    ("Ahri", "middle", [(8100, 8200), (8200, 8300), (8300, 8100)], [6655, 4645, 3089, 3157, 3135, 4646, 3165]),
    ("Jinx", "bottom", [(8000, 8300), (8000, 8100), (8300, 8000)], [3031, 3094, 3036, 3072, 3046, 3085, 3033]),
    ("Thresh", "utility", [(8400, 8300), (8300, 8400), (8400, 8200)], [3190, 3050, 3109, 3222, 3107, 2065]),
    ("LeeSin", "jungle", [(8000, 8100), (8100, 8000), (8000, 8400)], [6692, 3071, 6333, 3053, 6694, 3026]),
    ("Darius", "top", [(8000, 8400), (8400, 8000), (8000, 8300)], [3078, 6631, 3053, 3742, 6333, 3065]),
]
SHARDS = [(5008, 5008, 5011), (5005, 5008, 5011), (5008, 5010, 5001)]
BOOTS = [3020, 3006, 3047, 3111, 3158]
SPELLS = [(14, 4), (4, 12), (11, 4), (4, 3), (4, 7), (4, 21)]


def _page(runes: list[dict[str, Any]], primary: int, sub: int, rng: random.Random) -> tuple[int, int, tuple[int, ...]]:
    styles = {s["id"]: s for s in runes}
    p, s = styles[primary], styles[sub]
    keystone = rng.choice(p["slots"][0]["runes"])["id"]
    minors = [rng.choice(slot["runes"])["id"] for slot in p["slots"][1:4]]
    sub_slots = rng.sample(s["slots"][1:4], 2)
    secondary = [rng.choice(slot["runes"])["id"] for slot in sub_slots]
    return primary, sub, (keystone, *minors, *secondary)


def make_demo_builds(static: StaticData, runes: list[dict[str, Any]], cache: BuildCache) -> None:
    rng = random.Random(7)
    for champ, role, page_styles, core_pool in DEMO_CHAMPIONS:
        try:
            key = static.champions.key_of(champ)
        except KeyError:
            continue
        core_pool = [i for i in core_pool if static.items.is_completed(i)] or [
            i for i in static.items.items if static.items.is_completed(i)
        ][:8]
        pages = [_page(runes, p, s, rng) for p, s in page_styles]
        cores = [tuple(rng.sample(core_pool, 3)) for _ in range(3)]
        boots_pool = [b for b in BOOTS if static.items.is_boots(b)] or [0]
        records = []
        weights = [0.45, 0.3, 0.25]
        page_wr = [rng.uniform(0.49, 0.56) for _ in pages]
        for n in range(rng.randint(420, 900)):
            i = rng.choices(range(len(pages)), weights)[0]
            primary, sub, perks = pages[i]
            core = rng.choices(cores, [0.6, 0.25, 0.15])[0]
            boots = rng.choice(boots_pool[:2])
            situ = tuple(rng.sample([x for x in core_pool if x not in core], 2))
            spells = rng.choices(SPELLS, [0.4, 0.25, 0.15, 0.1, 0.05, 0.05])[0]
            starter = [1056, 2003] if role == "middle" else [1055, 2003] if role == "bottom" else [3865] if role == "utility" else [1102] if role == "jungle" else [1054, 2003]
            purchases = tuple((s, 1000) for s in starter) + tuple((it, 400_000 + k * 300_000) for k, it in enumerate((boots, *core)))
            records.append(ParticipantRecord(
                match_id=f"DEMO_{champ}_{n}", champion_id=key, position=role,
                win=rng.random() < page_wr[i] + (0.03 if core == cores[0] else 0),
                primary_style=primary, sub_style=sub,
                perks=(*perks, *rng.choices(SHARDS, [0.6, 0.25, 0.15])[0]),
                spells=spells, items=(*core, boots, *situ, 3340), purchases=purchases,
            ))
        params = SelectionParams(min_pick_rate=0.05, min_games=20, min_champion_games=30, max_variants=3)
        build = aggregate_build(records, champion=champ, champion_id=key, role=role, patch=static.patch,
                                items=static.items, params=params, source="demo")
        build.fetched_at = date.today().isoformat()
        cache.save(build)


# Cycle de la démo (secondes) : prépick (rien puis Ahri déclarée), mon ban, tour des autres, mon pick (Ahri survolée),
# Ahri verrouillée, puis la partie (joueurs fictifs).
DEMO_STEPS = [("empty", 5), ("planning", 6), ("ban", 12), ("wait", 6), ("pick", 10), ("locked", 15), ("ingame", 20)]
# Bans suggérés affichés pendant le tour de ban de la démo (pas d'appel OP.GG en démo).
DEMO_BANS = [  # (championId, winrate du champion contre Ahri, parties)
    (238, 0.531, 6120), (7, 0.528, 4380), (55, 0.524, 3950), (105, 0.519, 4210), (134, 0.512, 7990), (517, 0.508, 2870),
]


def demo_step(now: float, start: float) -> tuple[str, float]:
    """(étape du cycle, heure de fin de l'étape)."""
    t = (now - start) % sum(d for _, d in DEMO_STEPS)
    end = 0.0
    for name, duration in DEMO_STEPS:
        end += duration
        if t < end:
            return name, now + end - t
    raise AssertionError("unreachable")


def demo_session(me: int, phase_ends: float, step: str = "locked") -> dict[str, Any]:
    total = dict(DEMO_STEPS)[step] * 1000
    picked = me if step == "locked" else 0
    intent = 0 if step in ("locked", "empty") else me  # Ahri déclarée pendant le prépick, comme dans le client
    planning = step in ("empty", "planning")
    allies = [(1, 86, "top"), (2, 64, "jungle"), (3, picked, "middle"), (4, 222, "bottom"), (5, 0, "utility")]
    mine = [
        # Comme le vrai client : pendant le prépick, le ban est déjà marqué « en cours ».
        {"id": 3, "actorCellId": 3, "type": "ban", "championId": 0 if planning or step == "ban" else 7,
         "completed": not planning and step != "ban", "isInProgress": planning or step == "ban", "isAllyAction": True},
        {"id": 13, "actorCellId": 3, "type": "pick", "championId": picked or intent,
         "completed": step == "locked", "isInProgress": step == "pick", "isAllyAction": True},
    ]
    return {
        "localPlayerCellId": 3,
        "myTeam": [
            {"cellId": c, "championId": ch, "championPickIntent": 412 if c == 5 else intent if c == 3 else 0,
             "assignedPosition": pos, "spell1Id": 4, "spell2Id": 14}
            for c, ch, pos in allies
        ],
        "theirTeam": [{"cellId": c, "championId": ch}
                      for c, ch in [(6, 122), (7, 121), (8, 134 if step == "locked" else 0), (9, 51), (10, 89)]],
        "actions": [[
            {"type": "ban", "completed": True, "championId": 157, "isAllyAction": True},
            {"type": "ban", "completed": True, "championId": 555, "isAllyAction": True},
            {"type": "ban", "completed": True, "championId": 238, "isAllyAction": False},
            {"type": "ban", "completed": True, "championId": 875, "isAllyAction": False},
            *mine,
        ]],
        "timer": {"phase": "PLANNING" if planning else "BAN_PICK",
                  "adjustedTimeLeftInPhase": max(0, int((phase_ends - time.time()) * 1000)),
                  "totalTimeInPhase": total},
    }


def _player(name: str, champion: int, position: str, rank: str | None, lp: int | None, games: int, winrate: float,
            champ: tuple[int, float, float] | None, tags: list[tuple[str, str]], **extra: Any) -> dict[str, Any]:
    return {"riotId": name, "championId": champion, "position": position, "status": "ok" if rank else "loading",
            "isMe": False, "rank": rank, "lp": lp, "games": games, "winrate": winrate,
            "champion": {"games": champ[0], "winrate": champ[1], "kda": champ[2]} if champ else None,
            "mains": [champion], "tags": [{"text": t, "kind": k} for t, k in tags], **extra}


def demo_team() -> dict[str, Any]:
    """Joueurs fictifs de la partie (aucun appel OP.GG en démo)."""
    allies = [
        _player("TopDiff#EUW", 86, "top", "Or II", 47, 212, 0.53, (88, 0.57, 2.9), [("Main Garen", "good")]),
        _player("JungleKing#EUW", 64, "jungle", "Platine IV", 12, 340, 0.47, (6, 0.33, 1.8), [("Saison difficile", "bad")]),
        _player("Miitos#EUW", 103, "middle", "Émeraude III", 63, 156, 0.55, (61, 0.59, 3.4), [("En série de victoires", "good")], isMe=True),
        _player("AdcEnjoyer#EUW", 222, "bottom", "Non classé", None, 0, 0.0, None, [("Peu joué Jinx cette saison", "bad")]),
        _player("Hookline#EUW", 412, "utility", None, None, 0, 0.0, None, []),
    ]
    enemies = [
        _player("Sangsue#EUW", 122, "top", "Or I", 80, 190, 0.51, (120, 0.55, 2.4), [("Main Darius", "good")]),
        _player("Insecte#EUW", 121, "jungle", "Platine III", 30, 260, 0.52, (40, 0.5, 3.1), []),
        _player("SphereNoire#EUW", 134, "middle", "Émeraude IV", 22, 301, 0.54, (95, 0.58, 3.8),
                [("Main Syndra", "good"), ("58 % sur Syndra", "good")], isOpponent=True,
                form={"games": 9, "wins": 6, "results": [True, True, True, False, True, False, True, False, True],
                      "kda": 3.6, "onChampion": 7, "streak": {"win": True, "count": 3}},
                matchup={"lane": "EVEN", "soloKill": "DISADVANTAGE",
                         "tip": "Dodging Syndra's Scatter the Weak (E) is difficult before level 6. After level 6, use Spirit Rush (R) to dodge and kill her."}),
        _player("Piltie#EUW", 51, "bottom", "Or III", 5, 150, 0.49, (30, 0.47, 2.2), []),
        _player("Aube#EUW", 89, "utility", "Platine II", 61, 220, 0.56, (70, 0.6, 3.9), [("Vétéran du rang", "info")]),
    ]
    return {"status": "ok", "players": allies, "enemies": enemies}


def demo_bans(me: int) -> dict[str, Any]:
    taken = {157, 555, 238, 875}
    picks = [{"championId": c, "winrate": wr, "games": g} for c, wr, g in DEMO_BANS if c not in taken]
    return {"mode": "threats", "championId": me, "role": "middle", "status": "ok", "picks": picks}


async def prepare_demo_builds(ctrl: Any) -> StaticData | None:
    """Données du jeu (téléchargées si besoin) + builds d'exemple dans `<cache>/demo/`."""
    dd = DataDragon(ctrl.cfg.cache_dir)
    static = dd.load_cached()
    splash_dir = ctrl.cfg.cache_dir / "assets" / "splash"
    splash_count = len(list(splash_dir.glob("*.jpg"))) if splash_dir.exists() else 0
    if (static is None or not (ctrl.cfg.cache_dir / "ui_static.json").exists()
            or splash_count < len(static.champions.by_key) // 2):
        # Premier lancement sans prefetch : on récupère nous-mêmes les données publiques du jeu.
        ctrl.state["notice"] = "Téléchargement des données du jeu (première fois, environ 1 minute)…"
        await ctrl.broadcast()
        try:
            static = await asyncio.to_thread(dd.ensure)
            await asyncio.to_thread(AssetStore(ctrl.cfg.cache_dir).ensure, static.version)
        except Exception as exc:
            log.error("Démo : téléchargement Data Dragon impossible : %s", exc)
            ctrl.state["notice"] = "Impossible de télécharger les données du jeu. Vérifie ta connexion puis relance la démo."
            await ctrl.broadcast()
            return None
        ctrl.state["notice"] = "reload"  # la page recharge les noms et images
        await ctrl.broadcast()
    ctrl.state["notice"] = None
    runes = json.loads((dd.dir / static.version / "runesReforged.json").read_text(encoding="utf-8"))
    ctrl.cache = BuildCache(ctrl.cfg.cache_dir / "demo")
    make_demo_builds(static, runes, ctrl.cache)
    ctrl.state["lastPrefetch"] = ctrl._last_prefetch()
    ctrl.champions = static.champions
    return static


async def start_demo(ctrl: Any) -> None:
    ctrl.state["connection"] = "demo"
    static = await prepare_demo_builds(ctrl)
    if static is None:
        return
    ctrl.lcu = DryRunLcu()
    ctrl.state["connection"] = "demo"
    ctrl.state["phase"] = "ChampSelect"
    ahri = static.champions.key_of("Ahri")

    async def loop() -> None:
        start = time.time()
        while True:
            step, ends = demo_step(time.time(), start)
            if step == "ingame":
                ctrl.state["phase"] = "InProgress"
                ctrl.state["team"] = demo_team()
                await ctrl.on_session(None)  # le build verrouillé reste affiché
                await asyncio.sleep(1)
                continue
            ctrl.state["phase"], ctrl.state["team"] = "ChampSelect", None
            if step == "empty":
                ctrl.state["applied"] = None  # nouvelle partie de la démo : rien n'est encore appliqué
            ctrl.state["banSuggestions"] = demo_bans(ahri) if step in ("planning", "ban") else None
            await ctrl.on_session(demo_session(ahri, ends, step))
            await asyncio.sleep(1)

    asyncio.create_task(loop())


def launch_demo(ctrl: Any) -> None:
    """Démarre la démo en tâche de fond (le serveur répond pendant le téléchargement)."""
    asyncio.create_task(start_demo(ctrl))


def launch_demo_builds(ctrl: Any) -> None:
    """Vrai client League, mais avec les builds d'exemple (pour tester avant le premier prefetch)."""

    async def run() -> None:
        if await prepare_demo_builds(ctrl):
            await ctrl.broadcast()
            await ctrl.lcu_loop()

    asyncio.create_task(run())
