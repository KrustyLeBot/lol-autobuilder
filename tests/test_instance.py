"""Lancement alors que le port est déjà pris : lolbuilds déjà ouvert, ou autre logiciel (aucun client League requis)."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lolbuilds.app.main import _existing_instance


def serve(page: bytes, focus: bool):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self):
            calls.append(self.path)
            self.send_response(200 if focus else 404)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, calls


@pytest.mark.parametrize("page, focus, expected", [
    (b"<html><title>autre logiciel</title></html>", True, False),       # le port appartient à autre chose
    (b"<!doctype html><title>lolbuilds</title>", False, None),         # ancienne version : on prévient seulement
    (b"<!doctype html><title>lolbuilds</title>", True, True),          # sa fenêtre est ramenée devant
])
def test_existing_instance(page, focus, expected):
    httpd, calls = serve(page, focus)
    try:
        assert _existing_instance(httpd.server_address[1]) is expected
        assert calls == ([] if expected is False else ["/api/focus"])
    finally:
        httpd.shutdown()


def test_nothing_answering_is_not_lolbuilds():
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # port libre : rien ne répond
    assert _existing_instance(port) is False
