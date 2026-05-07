# ADR-009 — Flux réponse email : branchement Airbnb vs SMTP + orphan recovery post_init

**Date** : 2026-04-26
**Statut** : Adopté

## Contexte

Deux problèmes apparus en utilisation :

1. Tous les emails passaient par SMTP, y compris les notifications Airbnb (`no-reply@airbnb.com`, `automated@airbnb.com`, etc.) — l'envoi échouait systématiquement et bloquait le pipeline.
2. Au redémarrage du bot, le dict `_en_attente_confirmation` (in-memory) était vide. Si un pending avait `statut=confirme` + `reponse_choisie` non-nulle, la confirmation était perdue : Julien avait validé la réponse mais elle n'était jamais envoyée.

## Décision

### Branchement dans `_executer_action(state, bot=None, chat_id=None)`

Trois chemins distincts :

**Chemin Airbnb (source=protonmail + expéditeur contient « airbnb ») :**
- Pas de SMTP (adresses no-reply@airbnb.com, automated@airbnb.com, etc.)
- Si demande d'avis (sujet contient commentaire/review/avis/laisser) → envoie le lien Airbnb reviews
- Sinon → message informatif « Email Airbnb traité »
- Retourne `True` (succès) sans appel SMTP

**Chemin email normal (source=protonmail, expéditeur non-Airbnb) :**
- `folder = item_data.get("folder") or "INBOX"` — protège contre `folder=None` dans les anciens pendings
- Appel SMTP via `ProtonMailClient.reply_to_email()`
- Log INFO avec résultat OK/ECHEC + folder + uid

**Chemin Airbnb natif (source=airbnb) :**
- Playwright `AirbnbClient.send_message()` via interface web

### Orphan recovery au démarrage (post_init)

`post_init` appelle `get_pending_confirme_orphelin()` → si un orphelin est trouvé :
1. Recharge dans `_en_attente_confirmation[chat_id]`
2. Envoie alerte Telegram : texte de la réponse + « Réponds OUI pour envoyer, NON pour annuler »

`get_pending_confirme_orphelin()` dans `pending.py` :
- `WHERE statut='confirme' AND reponse_choisie IS NOT NULL`
- `ORDER BY created_at DESC LIMIT 1`

## Raisons

- Le branchement par source + détection d'expéditeur évite de tenter un SMTP voué à l'échec sur les adresses no-reply.
- L'orphan recovery est la seule manière de ne pas perdre une confirmation entre deux vies du processus, puisque le state d'attente est en mémoire.
- Limiter le recovery au dernier orphelin (`LIMIT 1`) évite de spammer Julien si plusieurs anciens orphelins traînent en DB.

## Tests bout-en-bout réussis (2026-04-26)

| Test | Source | Résultat |
|------|--------|---------|
| Communauto (uid=1, INBOX) | protonmail | SMTP OK, email marqué lu |
| Zohra review (automated@airbnb.com) | protonmail | Informationnel, lien reviews envoyé |

Logs VPS confirmés :
- réponse envoyée à « Communauto Quebec » noreply@communauto.com
- email UID=1 marqué comme lu
- `_executer_action: SMTP reply OK folder=INBOX uid=1`
- `_executer_action: email Airbnb dans Proton — action informative, pas de SMTP`

## Conséquences

- `/root/julien_os/main.py` : `_executer_action` avec branche Airbnb + signature `bot/chat_id` + orphan recovery dans `post_init`.
- `/root/julien_os/memory/pending.py` : ajout de `get_pending_confirme_orphelin()`.
