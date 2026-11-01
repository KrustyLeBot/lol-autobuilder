## Corrections

- **« lolbuilds est déjà ouvert (ou le port 8765 est occupé) » alors qu'il ne l'était pas** : sur certains PC, le port local 8765 est pris par un autre logiciel ou réservé par Windows (fréquent avec Hyper-V, WSL ou Docker). lolbuilds prend maintenant le port libre suivant et démarre normalement.
- **lolbuilds relancé alors qu'il tourne déjà** : sa fenêtre revient au premier plan au lieu d'afficher un message.

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
