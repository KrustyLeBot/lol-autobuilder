# lolbuilds : import automatique de builds LoL, sans Blitz

Pendant la sélection des champions, ce petit outil applique automatiquement **runes**, **sorts d'invocateur** et **item set** pour le champion choisi.

- Les builds viennent d'**OP.GG** (serveur MCP public, sans clé API) : statistiques classées Émeraude+ sur des centaines de milliers de parties.
- **Au moment du pick**, l'interface récupère le build du champion (un appel, 1 à 2 s), puis les builds **contre ton adversaire de lane** dès qu'il est connu. Tout est gardé en cache dans `~/.lolbuilds/` **jusqu'au lendemain** : le même build ou le même duel n'est jamais redemandé dans la journée.
- **Optionnel** : un prefetch nocturne récupère tous les champions à l'avance (`[prefetch] nightly = true`). Avec `[opgg] live = false`, l'interface ne fait plus aucun appel réseau et lit uniquement ce cache.
- La source de builds est **pluggable** : voir `BuildSource`.

## Interface

Lance-la avec `python -m lolbuilds.app` (ou `pythonw` pour ne pas avoir de console). Elle s'ouvre dans une fenêtre de bureau qui se connecte toute seule au client League.

- **Champ select en direct** : quand tu survoles ou verrouilles un champion, ses builds s'affichent avec le splash, la composition des deux équipes, les bans et le minuteur.
- **Build global** : la page de runes, les sorts et les items recommandés par OP.GG pour le champion dans son rôle, avec winrate et nombre de parties. Les champions joués dans plusieurs rôles ont un onglet par rôle.
- **Builds contre ton adversaire** : jusqu'à 2 pages de runes différentes, triées par winrate, avec les sorts et les items qui marchent le mieux dans ce duel. Elles s'affichent avant le build global et, avec Auto, la meilleure est appliquée automatiquement (sauf si tu as déjà choisi un build à la main).
- **Détection de l'adversaire** : le client ne donne pas la lane des ennemis. Elle est devinée d'après les rôles OP.GG de leurs champions (« deviné » s'affiche). Un clic sur un ennemi le choisit comme adversaire, un second clic revient à la détection.
- **Bons picks avant de choisir** : si l'adversaire de ta lane a choisi avant toi, jusqu'à 8 champions qui le battent sont proposés (winrate dans ce duel sur OP.GG, au moins 300 parties). Seuls les champions que tu possèdes (ou gratuits cette semaine), ni bannis ni pris, sont listés ; tes 15 meilleures maîtrises sont signalées. Un clic affiche le build de ce champion contre l'adversaire, sans rien sélectionner dans le client.
- **Ton tour** : quand c'est à toi de bannir ou de choisir, un bandeau l'indique et se remplit à mesure que le temps passe. Avec **Alerte** (barre du haut), la fenêtre repasse au premier plan et un son est joué.
- **Réglages** (rail de gauche) : alertes (premier plan, volume, un son au choix pour ton tour de ban, ton tour de pick, le début des bans, des picks et du champ select, avec écoute), application automatique, touche de Flash, et **thème**. Les raccourcis de la barre du haut restent disponibles.
- **Thèmes de région** : Hextech (défaut, maillage d'hexagones), Noxus, Piltover (clair) et Ionia. Chaque région a l'illustration, le blason et l'emblème officiels du site Univers de Riot (téléchargés une fois au démarrage dans `~/.lolbuilds/assets/realms/`), sa police de titre (Cinzel, Marcellus, Cormorant Garamond, embarquées) et ses formes de cartes. Les visuels de Riot sont utilisés dans le cadre de sa politique pour les projets de fans (usage personnel, non commercial).
- **Un clic sur une proposition l'applique au client** : page de runes, sorts d'invocateur et item set. Les touches `1` à `3` font la même chose.
- **Sorts d'invocateur** : appliqués avec le build. Flash est placé sur D ou F selon le réglage de la barre du haut.
- **Auto** : si l'option est activée, la proposition préférée est appliquée dès que le champion est verrouillé. La préférence est mémorisée par champion et par rôle quand tu en choisis une à la main.
- **Builds** : la liste de tous les builds en cache, avec winrate, échantillon et date de mise à jour. Un clic ouvre l'aperçu.
- **Bouton épingle** : garde la fenêtre au premier plan pendant le champ select.

| Commande | Effet |
|---|---|
| `python -m lolbuilds.app` | fenêtre de bureau |
| `python -m lolbuilds.app --demo` | faux champ select avec des builds d'exemple ; rien n'est envoyé au client |
| `python -m lolbuilds.app --demo-builds` | vrai client, builds d'exemple (sans OP.GG) |
| `python -m lolbuilds.app --browser` | ouvre l'interface dans le navigateur (http://127.0.0.1:8765) |

Les images et les textes en français (Data Dragon) sont mis à jour au démarrage de l'interface.

## Architecture

```
src/lolbuilds/
  sources/base.py            interface BuildSource (prepare / fetch_build / main_role)
  sources/opgg.py            source par défaut : serveur MCP d'OP.GG
  ddragon.py                 Data Dragon (champions, items, runes, sorts) en cache
  live.py                    récupération au pick + détection de l'adversaire, cache d'une journée
  targets.py                 filtre --only
  cache.py                   un fichier {Champion}_{role}.json, écriture atomique
  prefetch.py                job nocturne
  assets.py                  images et textes fr de l'interface (Data Dragon)
  aggregation.py             agrégation de parties (mode démo uniquement)
  app/                       interface : serveur local aiohttp + fenêtre pywebview
    lcu.py                   connexion LCU asynchrone (REST + WebSocket)
    applier.py               application d'un build : runes, sorts, item set
    server.py                état du champ select, actions, WebSocket vers la page
    demo.py                  mode démo
    ui/                      HTML/CSS/JS, polices embarquées
install_task.ps1             tâches planifiées Windows
```

### D'où viennent les builds

1. `lol_list_lane_meta_champions` (un appel par jour) donne, pour chaque champion, la part de ses parties dans chaque rôle. Ça sert à choisir le rôle quand le client n'en donne pas (blind, ARAM) et à deviner la lane des ennemis. Un rôle est proposé s'il dépasse `min_role_rate` (10 %) ; le rôle principal l'est toujours.
2. `lol_get_champion_analysis` (un appel par champion/rôle) donne la page de runes, les sorts, les items de départ, core, bottes et les options suivantes, chacun avec ses parties et victoires.
3. `lol_get_lane_matchup_guide` (un appel par duel) donne, contre un adversaire précis, 5 pages de runes, 5 paires de sorts et 15 chemins d'items. Les pages qui ne diffèrent que par les shards sont regroupées ; les 2 meilleures par winrate (pick ≥ 5 %, 50 parties) sont proposées, la plus jouée toujours incluse.
4. Les réponses sont relues sans exécuter de code (`ast`), converties en `Build` et écrites dans le cache. En cas d'erreur, **le dernier build connu est conservé**.

Le prefetch nocturne complet (~250 builds globaux) prend environ 7 minutes.

### Ajouter une autre source

```python
class MaSource(BuildSource):
    name = "ma-source"
    def fetch_build(self, champion: str, role: str) -> Build: ...
```

Il suffit ensuite de l'instancier dans `prefetch.make_source`.

## Installation

1. **Python 3.11 à 3.13**. `aiohttp` et `pywebview` ne sont pas garantis sur 3.14+.
   ```bash
   cd D:\dev\lol-autobuild
   ```
   ```bash
   py -3.13 -m venv .venv
   ```
   ```bash
   .venv\Scripts\pip install -e .[dev]
   ```
2. **Configuration** (optionnelle) : copier `config.example.toml` en `config.toml` pour changer l'elo des stats (`tier`), la touche de Flash, ou activer le prefetch nocturne. Aucune clé API n'est nécessaire.
3. **Planification** : l'interface à l'ouverture de session, plus la tâche de prefetch à 4 h (elle ne fait rien tant que `[prefetch] nightly = false`).
   ```bash
   powershell -ExecutionPolicy Bypass -File install_task.ps1 -WithApp
   ```

## Utilisation

| Commande | Effet |
|---|---|
| `python -m lolbuilds.prefetch` | met à jour tous les builds périmés (cache d'un autre jour), même si `nightly = false` |
| `python -m lolbuilds.prefetch --only Ahri` | uniquement Ahri, dans ses rôles suivis |
| `python -m lolbuilds.prefetch --only Thresh:utility --force` | rôle explicite, ignore la fraîcheur du cache |

Logs : `~/.lolbuilds/logs/app.log` et `prefetch.log`.

### Ce que fait l'interface en champ select

- Elle utilise `assignedPosition`. Si ce champ est vide (blind, ARAM…), elle prend le rôle principal du champion sur OP.GG.
- Avec Auto, le build est appliqué une fois le champion verrouillé, puis remplacé par le meilleur build contre l'adversaire quand il arrive, sauf si tu as choisi un build à la main.
- Les étapes se désactivent une à une dans `[champselect]` (`apply_runes`, `apply_spells`, `apply_item_set`).
- **Runes** : elle supprime les pages `[Auto]…`, puis crée une nouvelle page active. Si toutes les pages sont prises par tes pages perso, elle ne supprime rien et logue un avertissement.
- **Sorts** : elle les règle via `PATCH my-selection`, avec Flash sur la touche choisie (`flash_key`).
- **Item set** : elle relit tous les sets du compte et remplace uniquement ceux dont le titre commence par `[Auto]`. Le `PUT` du LCU remplace *tous* les sets, donc si la lecture échoue, rien n'est écrit.

## Tests

```bash
.venv\Scripts\python -m pytest
```

Les tests utilisent des réponses OP.GG enregistrées, des fixtures Data Dragon et des faux clients LCU et HTTP, **sans aucun appel réseau**.

## Limites connues

- **Adversaire deviné** : sur un champion polyvalent (Pantheon top ou support…), la lane devinée peut être fausse ; un clic sur le bon ennemi corrige. Si l'adversaire choisit en dernier, ses builds arrivent dans les dernières secondes.
- **Sans adversaire connu** : une seule proposition (le build global), OP.GG ne renvoyant pas d'alternative hors duel.
- **Serveur MCP d'OP.GG** : service public sans clé, dont le format et la disponibilité peuvent changer. En cas d'erreur, les builds de la veille restent en cache.
- **Début de patch** : les stats d'OP.GG mettent quelques heures à basculer sur le nouveau patch.
- **Endpoints LCU non officiels** : ils peuvent changer entre deux patchs. Chaque étape (runes, sorts, item set) est isolée, et les erreurs sont loguées sans faire planter le client.
