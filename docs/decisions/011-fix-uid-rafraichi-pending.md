# ADR-011 — UID IMAP rafraîchi pour les pending Proton existants

**Date** : 2026-04-27
**Statut** : Adopté

## Contexte

Quand ProtonMail réorganise sa boîte (déplacement, archivage, changement de label), un email garde son Message-ID mais reçoit un nouvel UID IMAP. Conséquences avant ce fix :

- Le watcher détectait correctement le doublon via Message-ID (`item_deja_traite=True`).
- Mais l'`item_data` du pending existant gardait l'ancien UID (par exemple `uid=5` alors que l'email était à `uid=4`).
- Si Julien validait OUI sur ce pending, `mark_as_read(uid="5")` ciblait un UID inexistant ou un autre email.
- Le rapport `/forcer_proton` disait juste « déjà traité » sans pointer vers le pending concerné — Julien ne savait pas où retrouver l'email dans `/pending`.

## Décision

Quand `item_deja_traite=True` dans le watcher Proton, charger le pending existant. Si `statut=en_attente` et que (`uid` ou `folder` a changé), rafraîchir `item_data.uid` et `item_data.folder` avec les valeurs courantes. Afficher la référence `folder#uid` dans `/pending` pour permettre à Julien de vérifier visuellement la cohérence.

### Fix appliqué

1. **`memory/pending.py`** — nouvelles fonctions :
   - `get_pending_by_item_id(source, item_id)` : retourne le dernier pending pour un Message-ID
   - `update_pending_item_data(pending_id, item_data)` : met à jour le JSON `item_data`

2. **`watchers/protonmail_watcher.py`** — quand `item_deja_traite=True` :
   - Charge le pending existant
   - Si `statut=en_attente` ET (`uid` ou `folder` a changé) : rafraîchit `item_data.uid` et `item_data.folder` avec les valeurs courantes
   - Rapport explicite : `pending #X — UID rafraîchi 5→4` ou `déjà traité — pending #X (en_attente)`

3. **`main.py` — cmd_pending** : affiche la référence `folder#uid` à côté de l'âge, ex. `[2] PROTONMAIL — 19h03 INBOX#4`. Permet à Julien de vérifier d'un coup d'œil que l'UID stocké correspond à l'email actuel.

## Raisons

- Sans rafraîchissement, le `mark_as_read` post-envoi cible le mauvais email (ou rien) : effet de bord silencieux mais visible côté Proton (l'email auquel on a répondu reste non lu).
- L'affichage `folder#uid` dans `/pending` rend les divergences immédiatement visibles, sans que Julien ait besoin de creuser dans les logs.
- Limiter le rafraîchissement aux pending `en_attente` évite de modifier l'historique des pendings déjà résolus.
