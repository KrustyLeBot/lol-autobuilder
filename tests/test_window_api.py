"""Épingle de la fenêtre : état suivi côté appli, jeu plein écran prioritaire, aucune exception vers la page."""

from __future__ import annotations

from lolbuilds.app import main as app_main
from lolbuilds.app.main import PinController


class Env:
    """Fenêtre et jeu simulés : `calls` garde chaque changement de « toujours au premier plan »."""

    def __init__(self):
        self.calls: list[bool] = []
        self.fullscreen = False
        self.pin = PinController(self.calls.append, lambda: self.fullscreen)


def test_toggle_pins_and_unpins():
    env = Env()
    assert env.pin.toggle() is True
    assert env.pin.toggle() is False
    assert env.calls == [True, False]


def test_pin_waits_while_a_fullscreen_game_has_the_focus():
    env = Env()
    env.fullscreen = True
    assert env.pin.toggle() is True and env.calls == []  # voulu, mais pas appliqué devant le jeu
    env.pin.poll()
    assert env.calls == []
    env.fullscreen = False
    env.pin.poll()
    assert env.calls == [True]  # le jeu est fermé : l'épingle s'applique


def test_pin_steps_back_for_a_game_then_returns():
    env = Env()
    env.pin.toggle()
    env.fullscreen = True
    env.pin.poll()
    env.pin.poll()  # pas de répétition
    assert env.calls == [True, False] and env.pin.pinned and env.pin.suspended
    env.fullscreen = False
    env.pin.poll()
    assert env.calls == [True, False, True] and not env.pin.suspended


def test_unpin_while_suspended_does_not_touch_the_window():
    env = Env()
    env.pin.toggle()
    env.fullscreen = True
    env.pin.poll()
    assert env.pin.toggle() is False
    assert env.calls == [True, False]  # déjà retirée pour le jeu


def test_bring_to_front_is_brief_unless_pinned_and_skipped_for_a_game(monkeypatch):
    monkeypatch.setattr(app_main.time, "sleep", lambda _s: None)
    env = Env()
    assert env.pin.bring_to_front() is True and env.calls == [True, False]
    env.calls.clear()
    env.pin.toggle()
    env.calls.clear()
    assert env.pin.bring_to_front() is True and env.calls == []  # épinglée : déjà devant
    env.pin.toggle()
    env.calls.clear()
    env.fullscreen = True
    assert env.pin.bring_to_front() is False and env.calls == []  # le jeu garde la priorité


def test_window_api_never_raises_to_the_page(monkeypatch):
    def boom(_window, _on_top):
        raise RuntimeError("fenêtre indisponible")

    monkeypatch.setattr(app_main, "_set_top_most", boom)
    monkeypatch.setattr(app_main, "fullscreen_app_active", lambda: False)
    api = app_main.WindowApi()
    api._window = object()
    assert api.toggle_on_top() is False  # reste non épinglée, sans exception
    api.pin = PinController(lambda _v: None, lambda: False)

    class Win:
        def restore(self):
            raise RuntimeError("x")

    api._window = Win()
    api.focus()  # ne lève pas


def test_focus_skipped_for_fullscreen_game(monkeypatch):
    monkeypatch.setattr(app_main, "fullscreen_app_active", lambda: True)
    api = app_main.WindowApi()
    api._window = None  # toucher la fenêtre lèverait : il ne doit rien se passer
    api.focus()
