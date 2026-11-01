"""Modèles de données partagés : build en cache et cible champion/rôle."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any


@dataclass(frozen=True, order=True)
class Target:
    """Un couple champion/rôle à suivre. `champion` = id Data Dragon (ex : "MonkeyKing")."""

    champion: str
    role: str


@dataclass
class Build:
    """Build prêt à appliquer ; sérialisé tel quel dans `{Champion}_{role}.json`."""

    champion: str
    champion_id: int
    role: str
    fetched_at: str  # date ISO (AAAA-MM-JJ) du dernier fetch réussi
    patch: str
    name: str
    primaryStyle: int
    subStyle: int
    perks: list[int]  # 9 ids : 4 primaires, 2 secondaires, 3 shards (offense, flex, défense)
    spells: list[int]  # [D, F]
    itemSet: dict[str, Any]
    sample_size: int
    winrate: float
    source: str = ""
    details: dict[str, Any] = field(default_factory=dict)  # stats de sélection (debug)
    # Propositions de build (la 1re = le build à plat ci-dessus), triées par winrate.
    variants: list[dict[str, Any]] = field(default_factory=list)
    # Paires de sorts proposées au choix : [{"spells": [14, 4], "games", "winrate", "pick_rate"}]
    spell_options: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Build:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def variant(self, index: int) -> Build:
        """Copie du build avec la variante `index` à plat (prête à appliquer)."""
        if not self.variants:
            return self
        v = self.variants[index]
        return replace(
            self,
            primaryStyle=v["primaryStyle"],
            subStyle=v["subStyle"],
            perks=list(v["perks"]),
            spells=list(v["spells"]),
            itemSet={**self.itemSet, "blocks": v["blocks"]},
            details=v.get("details", {}),
        )

    def validate(self) -> None:
        """Vérifications minimales avant écriture / application."""
        if len(self.perks) != 9:
            raise ValueError(f"{self.name} : 9 perks attendus, {len(self.perks)} reçus")
        if len(self.spells) != 2:
            raise ValueError(f"{self.name} : 2 sorts attendus, {len(self.spells)} reçus")
