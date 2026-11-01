"""Récupération des builds au moment du pick, avec cache disque d'une journée.

Utilisé par l'interface pendant le champ select (méthodes bloquantes : à appeler
via `asyncio.to_thread`). Tout ce qui est récupéré est gardé jusqu'au lendemain,
pour ne jamais rappeler OP.GG deux fois pour la même chose dans la journée :

  - `<cache>/{Champion}_{role}.json`              build global (même fichier que le prefetch) ;
  - `<cache>/matchups/{Champion}_{role}_vs_{Adversaire}.json`  propositions contre un adversaire ;
  - `<cache>/counters/{Ennemi}_{role}.json`      winrate de chaque champion contre un ennemi (bons picks) ;
  - `<cache>/opgg/tier_{role}.json`              tier list du rôle (bans suggérés) ;
  - `<cache>/opgg/lanes.json`                    rôles joués par champion (détection de l'adversaire).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date
from itertools import permutations
from pathlib import Path
from typing import Any

from . import ROLES
from .assets import AssetStore
from .cache import BuildCache
from .config import Config
from .ddragon import DataDragon, StaticData
from .models import Build
from .sources import BuildSourceError
from .sources.opgg import OpggSource

log = logging.getLogger(__name__)


def guess_lanes(enemies: list[str], roles: dict[str, dict[str, float]]) -> dict[str, str]:
    """Rôle le plus probable de chaque ennemi : affectation qui maximise la somme des role_rate."""
    known = [e for e in enemies if e]
    if not known:
        return {}
    best: tuple[float, tuple[str, ...]] = (-1.0, ())
    for combo in permutations(ROLES, len(known)):
        score = sum(roles.get(champ, {}).get(role, 0.0) for champ, role in zip(known, combo))
        if score > best[0]:
            best = (score, combo)
    return {champ: role for champ, role in zip(known, best[1]) if roles.get(champ, {}).get(role, 0.0) > 0}


class LiveBuilds:
    def __init__(self, cfg: Config, cache: BuildCache, source: OpggSource | None = None) -> None:
        self.cfg = cfg
        self.cache = cache
        self.dir = cfg.cache_dir
        self._source = source
        self._static: StaticData | None = source.static if source else None
        self._lock = threading.Lock()  # le client OP.GG n'est pas partagé entre threads
        self._roles: dict[str, dict[str, float]] | None = None
        self._roles_date = ""

    # ------------------------------------------------------------------ données statiques

    def refresh_static(self) -> bool:
        """Data Dragon + images de l'interface (une fois au démarrage). True si quelque chose a changé."""
        dd = DataDragon(self.dir)
        previous = self._static or dd.load_cached()
        before = previous.version if previous else None
        try:
            static = dd.ensure()
            AssetStore(self.dir).ensure(static.version)
        except Exception as exc:
            log.warning("Données du jeu non mises à jour : %s", exc)
            static = dd.load_cached()
        if static:
            self._static = static
            if self._source:
                self._source.static = static
        return bool(static) and static.version != before

    @property
    def static(self) -> StaticData:
        if self._static is None:
            self._static = DataDragon(self.dir).load_cached()
        if self._static is None:
            raise BuildSourceError("données du jeu absentes (Data Dragon)")
        return self._static

    @property
    def source(self) -> OpggSource:
        if self._source is None:
            self._source = OpggSource(self.static, self.cfg.opgg)
        return self._source

    # ------------------------------------------------------------------ rôles

    def roles(self) -> dict[str, dict[str, float]]:
        today = date.today().isoformat()
        path = self.dir / "opgg" / "lanes.json"
        with self._lock:
            if self._roles is None or self._roles_date != today:
                cached = _read(path)
                if cached and cached.get("date") == today:
                    self._roles = cached["roles"]
                else:
                    self._roles = self.source.roles()
                    _write(path, {"date": today, "roles": self._roles})
                self._roles_date = today
            return self._roles

    def champion_roles(self, champion: str) -> list[str]:
        """Rôles suivis pour le champion (même règle que le prefetch)."""
        rates = self.roles().get(champion) or {}
        if not rates:
            return []
        main = max(rates, key=rates.get)
        return [r for r in ROLES if r in rates and (r == main or rates[r] >= self.cfg.opgg.min_role_rate)]

    def role_for(self, champion: str, position: str) -> str | None:
        if position in ROLES:
            return position
        rates = self.roles().get(champion)
        return max(rates, key=rates.get) if rates else None

    def guess_opponent(self, enemies: list[str], my_role: str) -> str | None:
        lanes = guess_lanes(enemies, self.roles())
        return next((champ for champ, role in lanes.items() if role == my_role), None)

    # ------------------------------------------------------------------ builds

    def global_build(self, champion: str, role: str) -> Build | None:
        """Build du jour : cache s'il date d'aujourd'hui, sinon OP.GG (et l'ancien cache en secours)."""
        today = date.today()
        if self.cache.is_fresh(champion, role, today):
            return self.cache.load(champion, role)
        try:
            with self._lock:
                build = self.source.fetch_build(champion, role)
            build.fetched_at = today.isoformat()
            self.cache.save(build)
            log.info("OP.GG : build %s %s récupéré", champion, role)
            return build
        except (BuildSourceError, ValueError, OSError) as exc:
            log.warning("OP.GG : build %s %s indisponible (%s)", champion, role, exc)
            return self.cache.load(champion, role)

    def matchup(self, champion: str, role: str, opponent: str) -> list[dict[str, Any]]:
        """Propositions contre `opponent`, gardées pour la journée."""
        today = date.today().isoformat()
        path = self.dir / "matchups" / f"{champion}_{role}_vs_{opponent}.json"
        cached = _read(path)
        if cached and cached.get("date") == today:
            return cached["variants"]
        try:
            with self._lock:
                variants = self.source.fetch_matchup(champion, role, opponent)
        except BuildSourceError as exc:
            log.warning("OP.GG : matchup %s vs %s indisponible (%s)", champion, opponent, exc)
            return cached["variants"] if cached else []
        _write(path, {"date": today, "variants": variants})
        log.info("OP.GG : %s %s vs %s, %d propositions", champion, role, opponent, len(variants))
        return variants

    def tier_list(self, role: str) -> list[dict[str, Any]]:
        """Tier list OP.GG du rôle, gardée pour la journée."""
        today = date.today().isoformat()
        path = self.dir / "opgg" / f"tier_{role}.json"
        cached = _read(path)
        if cached and cached.get("date") == today:
            return cached["tiers"]
        try:
            with self._lock:
                tiers = self.source.fetch_tier_list(role)
        except BuildSourceError as exc:
            log.warning("OP.GG : tier list %s indisponible (%s)", role, exc)
            return cached["tiers"] if cached else []
        _write(path, {"date": today, "tiers": tiers})
        return tiers

    def counters(self, enemy: str, role: str) -> list[dict[str, Any]]:
        """Bons picks contre `enemy` (winrate de chaque champion contre lui), gardés pour la journée."""
        today = date.today().isoformat()
        path = self.dir / "counters" / f"{enemy}_{role}.json"
        cached = _read(path)
        if cached and cached.get("date") == today:
            return cached["counters"]
        try:
            with self._lock:
                counters = self.source.fetch_counters(enemy, role)
        except BuildSourceError as exc:
            log.warning("OP.GG : counters de %s indisponibles (%s)", enemy, exc)
            return cached["counters"] if cached else []
        _write(path, {"date": today, "counters": counters})
        log.info("OP.GG : %d picks évalués contre %s %s", len(counters), enemy, role)
        return counters

    def close(self) -> None:
        if self._source:
            self._source.close()


def _read(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
