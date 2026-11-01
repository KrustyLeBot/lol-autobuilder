## Corrections

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
