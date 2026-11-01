"""Agrégation pure (sans réseau) de parties en build, utilisée par le mode démo.

Règle de sélection, appliquée indépendamment à chaque composant (page de runes,
shards, sorts, items core, bottes, starter) :
  1. candidats éligibles = pick rate >= `min_pick_rate` ET parties >= `min_games` ;
  2. s'il y en a : meilleur winrate (à égalité, le plus joué) ;
  3. sinon : fallback sur le candidat le plus joué.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Hashable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from . import AUTO_PREFIX, ROLE_LABELS
from .ddragon import ItemCatalog
from .models import Build

K = TypeVar("K", bound=Hashable)

STARTER_WINDOW_MS = 90_000  # achats avant 1:30 = items de départ
CONSUMABLES = [2003, 2055]  # potion de soin, balise de contrôle


@dataclass(frozen=True)
class ParticipantRecord:
    """Ce qu'on garde d'un participant d'une partie classée."""

    match_id: str
    champion_id: int
    position: str  # rôle LCU en minuscules ("middle"...), "" si inconnu
    win: bool
    primary_style: int
    sub_style: int
    perks: tuple[int, ...]  # 9 ids
    spells: tuple[int, int]
    items: tuple[int, ...]  # inventaire final item0-6 (0 = vide)
    purchases: tuple[tuple[int, int], ...] = ()  # (item_id, timestamp_ms) dans l'ordre


# --------------------------------------------------------------------------- sélection

@dataclass(frozen=True)
class Choice(Generic[K]):
    key: K
    games: int
    wins: int
    total: int
    fallback: bool  # True si aucun candidat n'a passé les seuils

    @property
    def winrate(self) -> float:
        return self.wins / self.games if self.games else 0.0

    @property
    def pick_rate(self) -> float:
        return self.games / self.total if self.total else 0.0

    def describe(self) -> dict[str, Any]:
        return {
            "games": self.games,
            "winrate": round(self.winrate, 4),
            "pick_rate": round(self.pick_rate, 4),
            "fallback": self.fallback,
        }


def tally(samples: Iterable[tuple[K, bool]]) -> tuple[dict[K, list[int]], int]:
    """Compte [parties, victoires] par clé ; retourne aussi le total."""
    stats: dict[K, list[int]] = {}
    total = 0
    for key, win in samples:
        s = stats.setdefault(key, [0, 0])
        s[0] += 1
        s[1] += int(win)
        total += 1
    return stats, total


def select_best(stats: dict[K, list[int]], total: int, min_pick_rate: float, min_games: int) -> Choice[K] | None:
    """Applique la règle de sélection (voir docstring du module)."""
    if not stats or total == 0:
        return None
    eligible = [
        (k, g, w) for k, (g, w) in stats.items() if g / total >= min_pick_rate and g >= min_games
    ]
    if eligible:
        k, g, w = max(eligible, key=lambda t: (t[2] / t[1], t[1]))
        return Choice(k, g, w, total, fallback=False)
    k, (g, w) = max(stats.items(), key=lambda kv: (kv[1][0], kv[1][1]))
    return Choice(k, g, w, total, fallback=True)


def choose(
    records: Sequence[ParticipantRecord],
    key_fn: Callable[[ParticipantRecord], K | None],
    min_pick_rate: float,
    min_games: int,
) -> Choice[K] | None:
    """Sélectionne une clé ; les participants pour lesquels `key_fn` renvoie None sont ignorés."""
    samples = ((k, r.win) for r in records if (k := key_fn(r)) is not None)
    stats, total = tally(samples)
    return select_best(stats, total, min_pick_rate, min_games)


# --------------------------------------------------------------------------- clés de build

def rune_page_key(r: ParticipantRecord) -> tuple[int, int, tuple[int, ...]]:
    return (r.primary_style, r.sub_style, r.perks[:6])


def shards_key(r: ParticipantRecord) -> tuple[int, ...]:
    return r.perks[6:9]


def spells_key(r: ParticipantRecord) -> frozenset[int]:
    return frozenset(r.spells)


def core_items(r: ParticipantRecord, items: ItemCatalog) -> list[int]:
    """Items complétés (hors bottes) dans l'ordre d'achat ; inventaire final si pas de timeline."""
    source = [i for i, _ in r.purchases] if r.purchases else list(r.items[:6])
    seen: list[int] = []
    for iid in source:
        if items.is_completed(iid) and iid not in seen:
            seen.append(iid)
    return seen


def boots_of(r: ParticipantRecord, items: ItemCatalog) -> int | None:
    for iid in r.items[:6]:
        if items.is_boots(iid):
            return iid
    for iid, _ in r.purchases:
        if items.is_boots(iid):
            return iid
    return None


def starter_key(r: ParticipantRecord, items: ItemCatalog) -> tuple[int, ...] | None:
    if not r.purchases:
        return None
    start = tuple(sorted(i for i, t in r.purchases if t < STARTER_WINDOW_MS and items.is_starter(i)))
    return start or None


# --------------------------------------------------------------------------- build complet

@dataclass(frozen=True)
class SelectionParams:
    min_pick_rate: float = 0.05
    min_games: int = 20
    min_champion_games: int = 30
    max_variants: int = 3  # propositions de build par champion/rôle


class NotEnoughGames(Exception):
    pass


def pick_variant_pages(records: Sequence[ParticipantRecord], params: SelectionParams) -> list[tuple[Any, list[str], bool]]:
    """Pages de runes proposées : meilleurs winrates éligibles + toujours la plus jouée.

    Retourne [(clé de page, tags, fallback)] triée par winrate décroissant.
    Sans aucune page éligible : uniquement la plus jouée, marquée fallback.
    """
    stats, total = tally((rune_page_key(r), r.win) for r in records)
    most_played = max(stats.items(), key=lambda kv: (kv[1][0], kv[1][1]))[0]
    eligible = [
        k for k, (g, _w) in stats.items() if g / total >= params.min_pick_rate and g >= params.min_games
    ]
    if not eligible:
        return [(most_played, ["Le plus joué"], True)]

    def wr(k: Any) -> tuple[float, int]:
        g, w = stats[k]
        return (w / g, g)

    chosen = sorted(eligible, key=wr, reverse=True)[: params.max_variants]
    if most_played not in chosen:
        chosen[-1] = most_played
        chosen.sort(key=wr, reverse=True)
    result = []
    for i, k in enumerate(chosen):
        tags = (["Meilleur winrate"] if i == 0 else []) + (["Le plus joué"] if k == most_played else [])
        result.append((k, tags, False))
    return result


def build_variant(
    records: Sequence[ParticipantRecord], page_key: Any, total: int, items: ItemCatalog, params: SelectionParams,
) -> dict[str, Any]:
    """Build complet (shards, sorts, items) parmi les parties jouées avec une page de runes donnée."""
    sub = [r for r in records if rune_page_key(r) == page_key]
    pr, mg = params.min_pick_rate, max(3, params.min_games // 3)
    shards = choose(sub, shards_key, pr, mg)
    spell_pair = choose(sub, spells_key, pr, mg)
    assert shards is not None and spell_pair is not None
    core = None
    for size in (3, 2):
        core = choose(sub, lambda r, s=size: _prefix(core_items(r, items), s), pr, mg)
        if core:
            break
    boots = choose(sub, lambda r: boots_of(r, items), pr, mg)
    starter = choose(sub, lambda r: starter_key(r, items), pr, mg)
    excluded = set(core.key if core else ()) | ({boots.key} if boots else set())
    situational = _situational(sub, items, excluded, pr)

    blocks = []
    if starter:
        blocks.append(_block("starter", f"Départ ({_pct(starter)})", list(starter.key)))
    if core:
        blocks.append(_block("core", f"Core ({_pct(core)})", list(core.key)))
    if boots:
        blocks.append(_block("boots", f"Bottes ({_pct(boots)})", [boots.key]))
    if situational:
        blocks.append(_block("situational", "Situationnel", situational))
    blocks.append(_block("consumables", "Consommables", CONSUMABLES))

    primary, sub_style, perks6 = page_key
    wins = sum(r.win for r in sub)
    return {
        "primaryStyle": primary,
        "subStyle": sub_style,
        "perks": [*perks6, *shards.key],
        "spells": list(_dominant_order(sub, spell_pair.key)),
        "blocks": blocks,
        "games": len(sub),
        "winrate": round(wins / len(sub), 4),
        "pick_rate": round(len(sub) / total, 4),
        "details": {
            "shards": shards.describe(),
            "spells": spell_pair.describe(),
            "core": core.describe() if core else None,
            "boots": boots.describe() if boots else None,
            "starter": starter.describe() if starter else None,
        },
    }


def spell_options(records: Sequence[ParticipantRecord], params: SelectionParams, limit: int = 3) -> list[dict[str, Any]]:
    """Paires de sorts proposées au choix (meilleurs winrates éligibles + la plus jouée)."""
    stats, total = tally((spells_key(r), r.win) for r in records)
    ranked = sorted(stats.items(), key=lambda kv: (kv[1][1] / kv[1][0], kv[1][0]), reverse=True)
    eligible = [k for k, (g, _w) in ranked if g / total >= params.min_pick_rate and g >= params.min_games]
    most_played = max(stats.items(), key=lambda kv: kv[1][0])[0]
    keys = eligible[:limit]
    if most_played not in keys:
        keys = [*keys[: limit - 1], most_played]
    return [
        {
            "spells": list(_dominant_order(records, k)),
            "games": stats[k][0],
            "winrate": round(stats[k][1] / stats[k][0], 4),
            "pick_rate": round(stats[k][0] / total, 4),
            "most_played": k == most_played,
        }
        for k in keys
    ]


def aggregate_build(
    records: Sequence[ParticipantRecord],
    *,
    champion: str,
    champion_id: int,
    role: str,
    patch: str,
    items: ItemCatalog,
    params: SelectionParams,
    source: str = "demo",
) -> Build:
    """Construit le `Build` d'un champion/rôle : la meilleure variante à plat + toutes les variantes."""
    n = len(records)
    if n < params.min_champion_games:
        raise NotEnoughGames(f"{champion} {role} : {n} parties (< {params.min_champion_games})")

    variants = []
    for page_key, tags, fallback in pick_variant_pages(records, params):
        v = build_variant(records, page_key, n, items, params)
        v["tags"] = tags
        v["details"]["runes"] = {
            "games": v["games"], "winrate": v["winrate"], "pick_rate": v["pick_rate"], "fallback": fallback,
        }
        variants.append(v)
    best = variants[0]
    label = f"{champion} {ROLE_LABELS.get(role, role)}"
    wins = sum(r.win for r in records)
    return Build(
        champion=champion,
        champion_id=champion_id,
        role=role,
        fetched_at="",
        patch=patch,
        name=label,
        primaryStyle=best["primaryStyle"],
        subStyle=best["subStyle"],
        perks=best["perks"],
        spells=best["spells"],
        itemSet={
            "title": f"{AUTO_PREFIX} {label} {patch}",
            "associatedChampions": [champion_id],
            "associatedMaps": [11],
            "blocks": best["blocks"],
        },
        sample_size=n,
        winrate=round(wins / n, 4),
        source=source,
        details=best["details"],
        variants=variants,
        spell_options=spell_options(records, params),
    )


def _prefix(seq: list[int], size: int) -> tuple[int, ...] | None:
    return tuple(seq[:size]) if len(seq) >= size else None


def _dominant_order(records: Sequence[ParticipantRecord], pair: frozenset[int]) -> tuple[int, int]:
    """Ordre D/F le plus fréquent pour la paire de sorts choisie."""
    orders = Counter(r.spells for r in records if frozenset(r.spells) == pair)
    if not orders:
        a, b = sorted(pair) if len(pair) == 2 else (next(iter(pair)),) * 2
        return (a, b)
    return orders.most_common(1)[0][0]


def _situational(records: Sequence[ParticipantRecord], items: ItemCatalog, excluded: set[int], min_rate: float) -> list[int]:
    """Items complétés fréquents hors core/bottes, par fréquence décroissante (6 max)."""
    counts: Counter[int] = Counter()
    for r in records:
        for iid in set(r.items[:6]):
            if items.is_completed(iid) and iid not in excluded:
                counts[iid] += 1
    n = len(records)
    return [iid for iid, c in counts.most_common() if c / n >= min_rate][:6]


def _block(key: str, title: str, item_ids: Iterable[int]) -> dict[str, Any]:
    counts = Counter(item_ids)
    return {"key": key, "type": title, "items": [{"id": str(i), "count": c} for i, c in counts.items()]}


def _pct(choice: Choice[Any]) -> str:
    return f"{choice.winrate:.0%} WR, {choice.games} parties"
