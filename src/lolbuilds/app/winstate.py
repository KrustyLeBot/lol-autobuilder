"""État de Windows utile à l'alerte : une appli en plein écran (jeu, vidéo) a-t-elle la main ?"""

from __future__ import annotations

import sys

# SHQueryUserNotificationState : 2 = appli en plein écran, 3 = jeu Direct3D en plein écran exclusif,
# 4 = mode présentation. Les autres états (1 session absente, 5 normal, 6 heures calmes, 7 appli UWP) ne gênent pas.
BUSY_STATES = frozenset({2, 3, 4})


def fullscreen_app_active() -> bool:
    """Vrai quand une appli plein écran est au premier plan : on ne lui vole alors ni le focus ni le premier plan.

    C'est la même API que Windows utilise pour couper ses propres notifications pendant un jeu.
    Faux hors Windows ou si l'appel échoue : l'alerte reste alors comme avant."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        state = ctypes.c_int(0)
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
        return state.value in BUSY_STATES
    except Exception:  # noqa: BLE001
        return False
