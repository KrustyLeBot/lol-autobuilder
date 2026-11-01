"""Mise à jour depuis les releases GitHub : vérification, téléchargement vérifié (SHA-256), installation.

L'installation automatique ne concerne que l'exe installé par l'installateur (un `unins000.exe`
à côté de l'exe) : la version portable et l'installation depuis les sources ouvrent la page de la release.
"""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx

from . import __version__

log = logging.getLogger(__name__)

REPO = "Miitos/lol-autobuilder"
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
INSTALLER = re.compile(r"^lolbuilds-setup-.+\.exe$")
SUMS = "SHA256SUMS.txt"


class UpdateError(Exception):
    """Vérification ou téléchargement impossible (réseau, release incomplète, empreinte fausse)."""


def parse_version(text: str) -> tuple[int, ...]:
    """« v1.2.3 » -> (1, 2, 3) ; les suffixes (« -beta ») sont ignorés."""
    return tuple(int(n) for n in re.findall(r"\d+", text.split("-")[0])[:3]) or (0,)


def installed() -> bool:
    """Exe installé par l'installateur (et donc remplaçable par une nouvelle version de celui-ci)."""
    return bool(getattr(sys, "frozen", False)) and (Path(sys.executable).parent / "unins000.exe").exists()


def _client(http: httpx.Client | None) -> httpx.Client:
    return http or httpx.Client(timeout=30, follow_redirects=True,
                                headers={"User-Agent": f"lolbuilds/{__version__}", "Accept": "application/vnd.github+json"})


def check(current: str = __version__, http: httpx.Client | None = None) -> dict[str, Any]:
    """Dernière release : version, notes, liens. `newer` vaut True si elle est plus récente que `current`."""
    client = _client(http)
    try:
        resp = client.get(LATEST)
        resp.raise_for_status()
        release = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise UpdateError(f"GitHub injoignable ({exc})") from exc
    finally:
        if http is None:
            client.close()
    latest = str(release.get("tag_name", "")).lstrip("v")
    assets = {a.get("name", ""): a.get("browser_download_url", "") for a in release.get("assets") or []}
    installer = next((name for name in assets if INSTALLER.match(name)), None)
    return {
        "current": current,
        "latest": latest,
        "newer": parse_version(latest) > parse_version(current),
        "notes": str(release.get("body") or "")[:4000],
        "url": release.get("html_url") or f"https://github.com/{REPO}/releases/latest",
        "installer": {"name": installer, "url": assets[installer]} if installer else None,
        "sums": assets.get(SUMS),
    }


def download_installer(info: dict[str, Any], dest: Path, http: httpx.Client | None = None) -> Path:
    """Télécharge l'installateur de la release et vérifie son empreinte avec SHA256SUMS.txt."""
    installer = info.get("installer")
    if not installer or not info.get("sums"):
        raise UpdateError("la release ne contient pas d'installateur vérifiable")
    client = _client(http)
    try:
        sums = client.get(info["sums"])
        sums.raise_for_status()
        expected = next((line.split()[0].lower() for line in sums.text.splitlines()
                         if line.strip().endswith(installer["name"])), None)
        if not expected:
            raise UpdateError(f"empreinte de {installer['name']} absente de {SUMS}")
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / installer["name"]
        digest = hashlib.sha256()
        with client.stream("GET", installer["url"]) as resp:
            resp.raise_for_status()
            with path.open("wb") as f:
                for chunk in resp.iter_bytes():
                    digest.update(chunk)
                    f.write(chunk)
    except httpx.HTTPError as exc:
        raise UpdateError(f"téléchargement impossible ({exc})") from exc
    finally:
        if http is None:
            client.close()
    if digest.hexdigest() != expected:
        path.unlink(missing_ok=True)
        raise UpdateError("l'empreinte du fichier téléchargé ne correspond pas : installation annulée")
    return path


def launch_installer(path: Path) -> None:
    """Lance l'installateur en silencieux, détaché : il remplace l'appli (qui doit quitter) puis la relance."""
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CURRENTUSER"],
                     creationflags=flags, close_fds=True)
    log.info("Mise à jour : installateur %s lancé", path.name)
