"""Connexion asynchrone à l'API locale du client League (LCU).

L'UI a besoin d'une seule boucle asyncio partagée entre le serveur web et le
client LCU ; on lit donc nous-mêmes le port et le jeton dans la ligne de commande
de `LeagueClientUx.exe` (ou dans le lockfile), puis on ouvre HTTPS + WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
import psutil

log = logging.getLogger(__name__)

UX_PROCESS = ("LeagueClientUx.exe", "LeagueClientUx")
SUBSCRIPTIONS = (
    "OnJsonApiEvent_lol-champ-select_v1_session",
    "OnJsonApiEvent_lol-gameflow_v1_gameflow-phase",
)


@dataclass(frozen=True)
class Credentials:
    port: int
    token: str


def find_credentials() -> Credentials | None:
    """Port et jeton du client s'il tourne, sinon None."""
    for proc in psutil.process_iter(["name", "cmdline", "exe"]):
        try:
            if proc.info["name"] not in UX_PROCESS:
                continue
            args = proc.info["cmdline"] or []
            opts = dict(a[2:].split("=", 1) for a in args if a.startswith("--") and "=" in a)
            if "app-port" in opts and "remoting-auth-token" in opts:
                return Credentials(int(opts["app-port"]), opts["remoting-auth-token"])
            # Secours : le lockfile à côté de l'exécutable (LeagueClient:pid:port:password:https).
            exe = proc.info.get("exe")
            if exe:
                lock = Path(exe).parent / "lockfile"
                if lock.exists():
                    _, _, port, password, _ = lock.read_text().split(":")
                    return Credentials(int(port), password)
        except (psutil.Error, ValueError, OSError):
            continue
    return None


def encode_body(body: Any) -> bytes:
    """JSON compact en UTF-8 : le client refuse les requêtes trop volumineuses (413), et `json=` d'aiohttp ajoute des
    espaces et écrit chaque accent en \\uXXXX (6 octets au lieu de 2)."""
    return json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


class LcuConnection:
    """Requêtes REST + flux d'événements WebSocket sur le client local."""

    def __init__(self, creds: Credentials) -> None:
        self.base = f"https://127.0.0.1:{creds.port}"
        self.auth = aiohttp.BasicAuth("riot", creds.token)
        self.session = aiohttp.ClientSession(
            auth=self.auth,
            headers={"Accept": "application/json"},
            connector=aiohttp.TCPConnector(ssl=False),  # certificat auto-signé de Riot
            timeout=aiohttp.ClientTimeout(total=10),
        )
        self._ws_session: aiohttp.ClientSession | None = None

    async def close(self) -> None:
        await self.session.close()
        if self._ws_session:
            await self._ws_session.close()

    async def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        kwargs: dict[str, Any] = {}
        if body is not None:
            kwargs = {"data": encode_body(body), "headers": {"Content-Type": "application/json"}}
        async with self.session.request(method, self.base + path, **kwargs) as resp:
            try:
                data = await resp.json(content_type=None)
            except (json.JSONDecodeError, aiohttp.ContentTypeError):
                data = None
            return resp.status, data

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Événements {uri, eventType, data} jusqu'à la fermeture du client."""
        # Session dédiée : le LCU répond 404 à l'upgrade WebSocket sur une connexion
        # keep-alive déjà utilisée par une requête REST, ce que ferait le pool partagé.
        self._ws_session = aiohttp.ClientSession(auth=self.auth, connector=aiohttp.TCPConnector(ssl=False))
        async with self._ws_session.ws_connect(self.base.replace("https", "wss"), heartbeat=20) as ws:
            for topic in SUBSCRIPTIONS:
                await ws.send_json([5, topic])
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT or not msg.data:
                    continue
                try:
                    payload = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, list) and len(payload) == 3 and payload[0] == 8:
                    yield payload[2]


async def wait_for_client(poll: float = 2.0) -> Credentials:
    while True:
        creds = await asyncio.to_thread(find_credentials)
        if creds:
            return creds
        await asyncio.sleep(poll)
