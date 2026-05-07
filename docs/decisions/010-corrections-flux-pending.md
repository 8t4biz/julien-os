# ADR-010 — Corrections flux pending : no-reply, drop_pending_updates, expires_at

**Date** : 2026-04-26 (session 2)
**Statut** : Adopté

## Contexte

Trois problèmes identifiés en utilisation après le déploiement du flux pending :

1. SMTP tentait de répondre à des adresses no-reply (notifications automatiques) — échec systématique.
2. À chaque restart du bot, Telegram rejouait les anciens messages (par exemple « 3 » ou « NON » envoyés pendant les tests). Ces messages relançaient `handle_validation()` et appelaient `ignorer_pending()` sur des IDs sans que Julien le veuille.
3. `expires_at` faisait disparaître les pending de `/pending` après un délai, alors que Julien voulait pouvoir y revenir indéfiniment tant qu'il n'avait pas tranché.

## Décision

### Fix 1 : Détection no-reply avant SMTP

`_executer_action` vérifie l'adresse expéditeur **avant** d'appeler SMTP. Si elle contient l'un des patterns `noreply`, `no-reply`, `automated`, `do-not-reply`, `donotreply`, `do_not_reply` → SMTP bloqué.

Comportement :
- Airbnb review (`automated@` + sujet « commentaire/review/avis/laisser ») → « Texte prêt + lien Airbnb reviews »
- Autre no-reply → « Envoi bloqué : [adresse] est une adresse no-reply »
- Email normal (Clinique dentaire, consultant, etc.) → SMTP Proton Bridge comme avant

### Fix 2 : drop_pending_updates=True au démarrage du bot

`app.run_polling(drop_pending_updates=True)` ignore tous les messages Telegram arrivés pendant l'absence du bot. Julien doit renvoyer un message pour interagir après un restart.

### Fix 3 : expires_at retiré de get_pending_actif() et get_tous_pending_actifs()

Un pending `en_attente` reste visible dans `/pending` ET répondable (1/2/3) indéfiniment. Il ne disparaît que lorsque Julien répond : OUI → `envoye`, NON/3 → `ignore`. `expires_at` est conservé uniquement dans `get_pending_a_rappeler()` (pas de rappel automatique pour les vieux emails).

## Raisons

- Tester l'adresse en amont est plus simple que de gérer les erreurs SMTP cas par cas.
- Sans `drop_pending_updates`, chaque restart pendant un test pollue la DB avec des actions involontaires.
- L'expiration silencieuse des pending était trompeuse : un email visible une heure avant disparaissait du `/pending` sans que Julien comprenne pourquoi.

## Conséquences

- `/root/julien_os/main.py` — `_executer_action()` : remplacement du bloc `est_airbnb` par `NOREPLY_PATTERNS`.
- `/root/julien_os/main.py` — `app.run_polling(drop_pending_updates=True)` ajouté.
- `/root/julien_os/memory/pending.py` — `expires_at` retiré de `get_pending_actif()` et `get_tous_pending_actifs()`, conservé dans `get_pending_a_rappeler()`.
