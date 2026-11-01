"""lolbuilds : remplaçant léger de Blitz pour l'import automatique de builds LoL."""

__version__ = "0.2.1"

# Rôles canoniques (format LCU `assignedPosition`, en minuscules).
ROLES = ("top", "jungle", "middle", "bottom", "utility")

# Libellés courts utilisés dans les titres de pages de runes / item sets.
ROLE_LABELS = {
    "top": "Top",
    "jungle": "Jungle",
    "middle": "Mid",
    "bottom": "ADC",
    "utility": "Support",
}

# Préfixe des objets (pages de runes, item sets) créés par l'outil.
AUTO_PREFIX = "[Auto]"
