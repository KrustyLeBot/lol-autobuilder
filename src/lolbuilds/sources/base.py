"""Interface des sources de builds (pluggable).

Une source ne fait que *produire* un `Build` ; la fraîcheur du cache, le fallback
sur l'ancien build et l'écriture disque sont gérés par `prefetch`, pas par la source.
Pour brancher une autre source autorisée (partenaire, Leaguepedia...), il suffit
d'hériter de `BuildSource` et de l'instancier dans `prefetch.make_source`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..models import Build, Target


class BuildSourceError(Exception):
    """Erreur générique d'une source : le prefetch garde l'ancien cache."""


class InsufficientDataError(BuildSourceError):
    """Pas assez de données pour produire un build fiable (champion de niche, début de patch...)."""


class BuildSource(ABC):
    """Contrat minimal d'une source de builds."""

    #: identifiant court, recopié dans le champ `source` du cache
    name: str = "abstract"

    def prepare(self, targets: Sequence[Target]) -> None:
        """Hook optionnel appelé une fois par nuit avant les `fetch_build`.

        Permet à une source de faire un travail groupé (ex : télécharger un corpus
        de parties commun à tous les champions). Ne doit pas lever pour une erreur
        partielle : logguer et continuer avec les données disponibles.
        """

    @abstractmethod
    def fetch_build(self, champion: str, role: str) -> Build:
        """Retourne le build du champion (id Data Dragon) pour le rôle (format LCU).

        Lève `BuildSourceError` (ou une sous-classe) en cas d'échec.
        Le champ `fetched_at` est renseigné par l'appelant.
        """

    def main_role(self, champion: str) -> str | None:
        """Rôle le plus joué du champion selon la source, si elle le sait (sinon None)."""
        return None

    def close(self) -> None:
        """Libère les ressources (connexions, base SQLite...)."""
