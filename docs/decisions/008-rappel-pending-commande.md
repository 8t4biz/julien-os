# ADR-008 — Rappels automatiques pending et commande /pending

**Date** : 2026-04-26
**Statut** : Adopté

## Contexte

Les pending `en_attente` pouvaient être oubliés dans le fil Telegram si Julien ne répondait pas dans la même session. Aucun moyen non plus de lister les pending actifs sans remonter manuellement les messages.

## Décision

1. Job `job_rappel_pending` exécuté toutes les 3600 s (premier check 5 min après le démarrage du bot) qui renvoie l'alerte d'un pending sans réponse depuis plus de 4 h.
2. Commande `/pending` qui liste tous les pending `statut=en_attente` non expirés.

### Logique du rappel

- Cherche les pending `en_attente` depuis plus de 4 h sans réponse de Julien.
- Condition SQL : `created_at < now-4h` ET (`dernier_rappel_at IS NULL` OU `dernier_rappel_at < now-4h`).
- Renvoie l'alerte originale avec le préfixe « RAPPEL (Xh sans réponse) » + les 2 options + l'ID.
- Met à jour `dernier_rappel_at` après envoi → pas de re-rappel avant 4 h supplémentaires.

### Format /pending

- Affiche : `[ID] SOURCE - âge | De : ... | Sujet : ...`
- Tri du plus récent au plus ancien.

## Raisons

- Julien doit pouvoir reprendre les pending laissés en suspens sans chercher manuellement dans Telegram.
- Un rappel toutes les 4 h évite le spam (les emails ne sont pas tous urgents) tout en garantissant qu'un pending ne disparaît pas du radar.
- Le listage explicite via `/pending` est plus fiable que de remonter le fil de conversation.

## Conséquences

- `/root/julien_os/memory/pending.py` : ajout de `get_tous_pending_actifs()`, `get_pending_a_rappeler()`, `marquer_rappel_envoye()`.
- `/root/julien_os/main.py` : ajout de `cmd_pending`, `job_rappel_pending`, `run_repeating(3600)`, `CommandHandler("pending")`.
- Migration douce : `ALTER TABLE pending_actions ADD COLUMN dernier_rappel_at`.
