"""Épingle de la fenêtre : l'état suivi côté appli, et aucune exception ne remonte jusqu'à la page."""

from __future__ import annotations

from lolbuilds.app import main as app_main


class FakeWindow:
    uid = "master"

    def __init__(self):
        self.restored = 0

    def restore(self):
        self.restored += 1


def make_api(monkeypatch, fail: bool = False):
    calls: list[bool] = []

    def fake(_window, on_top):
        if fail:
            raise RuntimeError("fenêtre indisponible")
        calls.append(on_top)

    monkeypatch.setattr(app_main, "_set_top_most", fake)
    api = app_main.WindowApi()
    api._window = FakeWindow()
    return api, calls


def test_toggle_on_top_flips_and_reports_state(monkeypatch):
    api, calls = make_api(monkeypatch)
    assert api.toggle_on_top() is True
    assert api.toggle_on_top() is False
    assert calls == [True, False]


def test_toggle_failure_keeps_state_and_does_not_raise(monkeypatch):
    api, _ = make_api(monkeypatch, fail=True)
    assert api.toggle_on_top() is False  # reste non épinglée, sans exception


def test_focus_goes_briefly_on_top_unless_pinned(monkeypatch):
    monkeypatch.setattr(app_main.time, "sleep", lambda _s: None)
    api, calls = make_api(monkeypatch)
    api.focus()
    assert calls == [True, False] and api._window.restored == 1
    calls.clear()
    api.toggle_on_top()
    api.focus()
    assert calls == [True]  # épinglée : pas de passage supplémentaire
