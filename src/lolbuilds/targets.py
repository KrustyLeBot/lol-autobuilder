"""Filtre `--only` sur la liste des couples champion/rôle (fournie par la source)."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .ddragon import ChampionCatalog
from .models import Target

log = logging.getLogger(__name__)


def filter_only(targets: list[Target], only: list[str], champions: ChampionCatalog,
                fallback_role: Callable[[str], str | None]) -> list[Target]:
    """`--only Ahri` ou `--only Ahri:middle` : restreint (ou ajoute) les cibles demandées."""
    result: set[Target] = set()
    for spec in only:
        name, _, role = spec.partition(":")
        champ = champions.resolve(name)
        if not champ:
            log.error("--only : champion inconnu %r", name)
            continue
        if role:
            result.add(Target(champ, role.lower()))
            continue
        existing = [t for t in targets if t.champion == champ]
        if existing:
            result.update(existing)
        elif fb := fallback_role(champ):
            result.add(Target(champ, fb))
        else:
            log.error("--only %s : rôle inconnu, précisez-le (ex : %s:middle)", name, name)
    return sorted(result)
