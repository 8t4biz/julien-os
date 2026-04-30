# ADR-005 — Flags watcher en SQLite plutôt qu'en mémoire ou fichier

**Date** : 2026-04-08
**Statut** : Accepté

## Contexte

Les watchers doivent envoyer une alerte "session expirée" une seule fois, même après un redémarrage du bot.

## Décision

Flags persistants en SQLite dans `watchers/flags.py`, table `watcher_flags`.

## Raisons

- Flag en mémoire Python : perdu à chaque redémarrage → alertes en boucle
- Flag fichier (`Path.touch()`) : fonctionnel mais resets incorrects si `_verifier_session` retourne faux positif
- SQLite : survit aux redémarrages, partagé entre tous les watchers, atomique

## Règle critique

`marquer_alerte(cle)` doit être appelé **AVANT** `bot.send_message()`.
Si le bot crash entre les deux, le flag est déjà posé → pas de doublon au prochain démarrage.

## Conséquences

`watchers/flags.py` expose `alerte_deja_envoyee(cle)`, `marquer_alerte(cle)`, `reset_alerte(cle)`.
Clés utilisées : `airbnb_session`, `proton_session`.
