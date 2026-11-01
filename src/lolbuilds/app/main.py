"""Lance l'interface : serveur local + fenêtre de bureau (pywebview).

Usage :
    pythonw -m lolbuilds.app             # fenêtre, suit le client League
    python  -m lolbuilds.app --demo      # faux champ select, rien n'est écrit dans le client
    python  -m lolbuilds.app --demo-builds   # vrai client, builds d'exemple (écrit dans le client !)
    python  -m lolbuilds.app --browser   # ouvre l'UI dans le navigateur au lieu d'une fenêtre
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import threading
import time
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..config import default_config_path, load_config, setup_logging
from .server import Controller, start_server

log = logging.getLogger("lolbuilds.app")


class WindowApi:
    """Méthodes appelables depuis la page (window.pywebview.api.*) pour la barre de titre maison."""

    def __init__(self) -> None:
        self._window: Any = None

    def minimize(self) -> None:
        self._window.minimize()

    def close(self) -> None:
        self._window.destroy()

    def toggle_on_top(self) -> bool:
        self._window.on_top = not self._window.on_top
        return self._window.on_top

    def focus(self) -> None:
        """Ramène la fenêtre devant le client League (c'est au joueur de bannir ou de choisir)."""
        w = self._window
        w.restore()
        if w.on_top:  # épinglée : déjà au premier plan
            return
        # Windows refuse de voler le focus : un passage bref en « toujours au premier plan » suffit.
        w.on_top = True
        time.sleep(0.4)
        w.on_top = False


def serve_in_thread(ctrl: Controller, host: str, port: int) -> threading.Event:
    ready = threading.Event()
    errors: list[BaseException] = []

    def target() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(start_server(ctrl, host, port))
        except BaseException as exc:  # port déjà pris, etc.
            errors.append(exc)
            ready.set()
            return
        ready.set()
        loop.run_forever()

    threading.Thread(target=target, name="lolbuilds-server", daemon=True).start()
    ready.wait(15)
    if errors:
        raise errors[0]
    return ready


def run(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    setup_logging(cfg.cache_dir, "app", args.verbose)
    ctrl = Controller(cfg, demo=args.demo, demo_builds=args.demo_builds)
    url = f"http://127.0.0.1:{args.port}/"
    try:
        serve_in_thread(ctrl, "127.0.0.1", args.port)
    except OSError as exc:
        log.error("Port %d indisponible (%s) : l'application tourne peut-être déjà.", args.port, exc)
        if not args.browser:
            return 1
    log.info("Interface sur %s%s", url, " (démo)" if args.demo else "")

    if args.browser or args.server_only:
        if args.browser:
            webbrowser.open(url)
        threading.Event().wait()  # jusqu'à Ctrl+C
        return 0

    import webview  # import local : seulement pour le mode fenêtre

    api = WindowApi()
    api._window = webview.create_window(
        "lolbuilds", url + "?desktop=1", js_api=api, width=1240, height=800, min_size=(960, 640),
        frameless=True, easy_drag=False, background_color="#0A0D13",
    )
    webview.start()  # profil temporaire : les préférences sont côté serveur
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="lolbuilds-app", description=__doc__.splitlines()[0])
    p.add_argument("--config", type=Path, default=default_config_path())
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--demo", action="store_true", help="faux champ select avec builds d'exemple")
    p.add_argument("--demo-builds", action="store_true",
                   help="vrai client League, mais avec les builds d'exemple (avant le premier prefetch)")
    p.add_argument("--browser", action="store_true", help="ouvre l'UI dans le navigateur")
    p.add_argument("--server-only", action="store_true", help="serveur seul, sans fenêtre")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    sys.exit(run(parse_args(argv)))


if __name__ == "__main__":
    main()
