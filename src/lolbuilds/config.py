"""Chargement de `config.toml` en dataclasses typées."""

from __future__ import annotations

import logging
import os
import sys
import tomllib
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

OPGG_TIERS = ("", "all", "challenger", "grandmaster", "master_plus", "master", "diamond_plus", "diamond",
              "emerald_plus", "emerald", "platinum_plus", "platinum", "gold_plus", "gold", "ibsg", "silver",
              "bronze", "iron")


@dataclass(frozen=True)
class OpggSettings:
    tier: str = "emerald_plus"  # "" = défaut OP.GG
    game_mode: str = "ranked"
    min_role_rate: float = 0.10  # rôle suivi s'il représente au moins 10 % des parties du champion
    request_interval: float = 0.5  # s entre deux requêtes OP.GG
    live: bool = True  # récupère le build au moment du pick s'il n'est pas déjà en cache du jour
    matchup: bool = True  # + les builds contre l'adversaire de lane détecté

    def __post_init__(self) -> None:
        if self.tier not in OPGG_TIERS:
            raise ValueError(f"tier OP.GG inconnu : {self.tier!r} (attendu : {', '.join(t for t in OPGG_TIERS if t)})")


@dataclass(frozen=True)
class PrefetchSettings:
    nightly: bool = False  # la tâche planifiée (--scheduled) ne fait rien si False


@dataclass(frozen=True)
class ChampSelectSettings:
    """Ce que l'interface applique dans le client ([champselect] de config.toml)."""

    flash_key: str = "F"
    apply_runes: bool = True
    apply_spells: bool = True
    apply_item_set: bool = True


@dataclass(frozen=True)
class Config:
    opgg: OpggSettings = field(default_factory=OpggSettings)
    prefetch: PrefetchSettings = field(default_factory=PrefetchSettings)
    champselect: ChampSelectSettings = field(default_factory=ChampSelectSettings)
    cache_dir: Path = Path("~/.lolbuilds").expanduser()


def load_config(path: Path | None) -> Config:
    """Charge la config ; un fichier absent donne la config par défaut."""
    if path is None or not path.exists():
        return Config()
    with path.open("rb") as f:
        raw = tomllib.load(f)

    flash_key = str(raw.get("champselect", {}).get("flash_key", "F")).upper()
    if flash_key not in ("D", "F", ""):
        raise ValueError(f"flash_key doit valoir 'D', 'F' ou '' (reçu {flash_key!r})")
    cs_raw = dict(raw.get("champselect", {}), flash_key=flash_key)

    cache_dir = Path(os.path.expandvars(raw.get("paths", {}).get("cache_dir", "~/.lolbuilds"))).expanduser()
    return Config(
        opgg=OpggSettings(**raw.get("opgg", {})),
        prefetch=PrefetchSettings(**raw.get("prefetch", {})),
        champselect=ChampSelectSettings(**cs_raw),
        cache_dir=cache_dir,
    )


def default_config_path() -> Path:
    """`config.toml` : LOLBUILDS_CONFIG, sinon `~/.lolbuilds/` pour l'exe installé, sinon la racine du projet."""
    env = os.environ.get("LOLBUILDS_CONFIG")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):  # exe PyInstaller : le dossier d'installation n'est pas modifiable
        return Path("~/.lolbuilds/config.toml").expanduser()
    return Path(__file__).resolve().parents[2] / "config.toml"


def setup_logging(cache_dir: Path, name: str, verbose: bool = False) -> None:
    """Log console + fichier tournant dans `<cache>/logs/<name>.log` (indispensable sous pythonw)."""
    log_dir = cache_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s : %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    file_handler = RotatingFileHandler(log_dir / f"{name}.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)
    # Sous pythonw, sys.stderr vaut None : pas de handler console.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)
    logging.getLogger("httpx").setLevel(logging.WARNING)
