"""Visuels des thèmes de région (Noxus, Piltover, Ionia), depuis le site officiel Univers de Riot.

Le thème Hextech n'a pas d'illustration : son motif d'hexagones est dessiné en CSS.

Téléchargés une seule fois dans `<cache>/assets/realms/{thème}/` (bg.jpg, crest.png, emblem.png),
puis servis par l'interface sous `/assets/realms/...`. Un visuel manquant n'empêche rien :
le thème garde ses couleurs, ses polices et ses ornements.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

FACTIONS = "https://universe-meeps.leagueoflegends.com/v1/fr_fr/factions/{slug}/index.json"
IMAGES = "https://universe.leagueoflegends.com/images/{name}.png"
RESIZE = "&w=1600&q=70"  # l'image d'origine fait parfois 4 Ko px de large

# thème -> (faction Univers, préfixe des fichiers crest/emblem sur le site : Riot écrit « iona »)
REALMS: dict[str, tuple[str, str]] = {
    "noxus": ("noxus", "noxus"),
    "piltover": ("piltover", "piltover"),
    "ionia": ("ionia", "iona"),
}


def ensure_realm_assets(cache_dir: Path, http: httpx.Client | None = None) -> None:
    """Télécharge les visuels manquants ; les erreurs réseau sont seulement loguées."""
    root = cache_dir / "assets" / "realms"
    client = http or httpx.Client(timeout=30, follow_redirects=True)
    try:
        jobs: list[tuple[str, Path]] = []
        for realm, (slug, prefix) in REALMS.items():
            folder = root / realm
            if not (folder / "bg.jpg").exists():
                try:
                    faction = client.get(FACTIONS.format(slug=slug)).json()
                    jobs.append((faction["faction"]["image"]["uri"] + RESIZE, folder / "bg.jpg"))
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    log.warning("Thème %s : illustration introuvable (%s)", realm, exc)
            jobs.append((IMAGES.format(name=f"{prefix}_crest_icon"), folder / "crest.png"))
            jobs.append((IMAGES.format(name=f"{prefix}_emblem"), folder / "emblem.png"))
        for url, path in jobs:
            if path.exists():
                continue
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                log.warning("Visuel de thème non téléchargé %s : %s", url, exc)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
    finally:
        if http is None:
            client.close()
