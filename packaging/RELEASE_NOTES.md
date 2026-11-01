## Nouveautés

- **ARAM** : en ARAM, lolbuilds applique maintenant un build issu des statistiques d'ARAM d'OP.GG (runes, sorts, items et item set pour l'Abîme hurlant) au lieu d'un build de lane de la faille.
- **Build atypique** : dans les autres modes, le build ARAM du champion est proposé en dernier, étiqueté « Atypique : build ARAM ». Il n'est jamais appliqué par défaut.
- **Sorts d'invocateur** : un réglage permet d'appliquer le build et les runes sans jamais toucher à tes sorts (Réglages › Champ select).
- **Builds en cache** : un build ouvert depuis la bibliothèque s'affiche dans la bibliothèque et ne remplace plus ta sélection de champion en cours (tu vois toujours ton champ select et ton équipe).
- **Tout télécharger** récupère aussi les builds ARAM. Pour tout désactiver : `aram = false` dans `config.toml` (section `[opgg]`).

## Corrections

- **Item set refusé (413 « Content length is too large »)** : les requêtes vers le client sont maintenant envoyées en JSON compact (environ un quart plus léger), et si le client refuse encore l'item set parce que ceux du compte sont trop volumineux, l'appli l'explique (nombre et poids de tes item sets) au lieu d'une simple croix rouge.
- **Alerte de ton tour** : une erreur dans la page empêchait le son de retentir quand c'était à toi de bannir ou de choisir (avec « Fenêtre au premier plan » activé). Corrigé.
- **Ban en un clic** : pendant ton tour de ban, un clic sur un champion des bans suggérés le bannit directement (sélection et verrouillage en une fois, sans bouton de validation). Le verrouillage pouvait ne pas aboutir dans la version précédente. Ça ne touche jamais à ton pick, ni au prépick.
- **Journal** : chaque tentative de ban est notée dans `logs\app.log` avec la réponse du client, pour pouvoir diagnostiquer un refus.

## Mettre à jour

- Depuis la **0.2.0** ou plus récent : Réglages › Mise à jour › **Mettre à jour**.
- Le **zip portable** de la 0.2.1 (qui ne démarrait pas toujours) et la **0.1.0** n'ont pas ce bouton : télécharge l'installateur ou l'exe portable ci-dessous une fois ; les versions suivantes arriveront depuis l'application.

## Télécharger

| Fichier | Pour qui |
|---|---|
| `lolbuilds-setup-….exe` | **La plupart des joueurs** : installateur classique, sans droits administrateur |
| `lolbuilds-portable-….exe` | Sans installation : un seul fichier à lancer, qui se met à jour tout seul |
| `SHA256SUMS.txt` | Empreintes pour vérifier les fichiers |

Windows 10 ou 11 (64 bits). Au premier lancement, si Windows affiche « Windows a protégé votre ordinateur », clique sur **Informations complémentaires** puis **Exécuter quand même** (l'application n'est pas signée).

Mode d'emploi complet : voir le [README](https://github.com/Miitos/lol-autobuilder#readme).
