# ADR-006 — Flux Proton Mail bout-en-bout

**Date** : 2026-04-26
**Statut** : Adopté

## Contexte

Le watcher Proton Mail doit détecter les emails non lus, les classer par priorité, proposer à Julien deux options de réponse, et envoyer la réponse choisie via SMTP — le tout depuis Telegram. La première version souffrait de plusieurs défauts : double appel LLM coûteux, regex fragile pour extraire les options, FETCH RFC822 qui marquait les emails comme lus prématurément, scan limité à INBOX alors que les emails de Julien sont éclatés dans des sous-dossiers.

## Décision

Pipeline unifié :

```
Batch 11h45 / 17h EDT
       ↓
protonmail_watcher.poll_once()
  → ProtonMailClient.get_unread_emails()    # IMAP, emails non lus
  → ProtonMailClient.get_email_body_by_uid() # corps complet par UID
  → protonmail_agent.analyser_et_generer()  # 1 appel LLM → JSON structuré
       { priorite, contexte, option_courte, option_complete }
  → Si IGNORER → skip
  → creer_pending() en SQLite
  → Telegram : alerte HTML avec 2 options complètes lisibles
       ↓
Julien répond 1 / 2 / texte libre
       ↓
handle_validation() → confirmer_pending()
       ↓ (OUI)
_executer_action() → ProtonMailClient.reply_to_email()
  → SMTP Bridge envoie la réponse
  → mark_as_read(uid) → email marqué lu dans IMAP
  → Telegram : envoyé
```

Trois choix structurants :

1. Un seul appel LLM (`analyser_et_generer`) qui retourne JSON structuré `{priorite, contexte, option_courte, option_complete}` au lieu de deux appels successifs.
2. `FETCH (BODY.PEEK[])` au lieu de `FETCH (RFC822)` partout où on lit un email — identique en contenu mais ne pose pas le flag `\Seen`.
3. Scan multi-dossiers avec déduplication par Message-ID.

`FOLDERS_TO_SCAN` dans `ProtonMailClient` :
- INBOX
- Folders/[INC] Consulting
- Folders/[INC] Build
- Folders/[INC] Finance
- Folders/[FI]
- Folders/[PERSO]

## Raisons

- Deux appels LLM séparés (priorité puis options) coûtaient des tokens supplémentaires sans bénéfice — la fusion en un seul appel JSON simplifie aussi le parsing.
- `FETCH (RFC822)` posait `\Seen` à chaque scan : au premier scan l'email était détecté mais immédiatement marqué lu, au scan suivant `SEARCH UNSEEN` retournait vide → détection perpétuellement à 0.
- Scan limité à INBOX manquait tous les emails déjà classés par les filtres ProtonMail dans les sous-dossiers `Folders/[INC]*`, `[FI]`, `[PERSO]`.
- Regex fragile sur le texte des options remplacée par JSON structuré — plus aucun parsing texte sur la sortie LLM.
- Options tronquées à 150 caractères dans Telegram → `formater_alerte_telegram` affiche désormais les options complètes.

## Règle critique

`mark_as_read(uid)` ne doit être appelé qu'**après** l'envoi SMTP réussi, jamais pendant le scan. C'est le seul endroit qui pose `\Seen`.

## Conséquences

- `tools/protonmail.py` : `get_unread_emails()`, `get_email_body_by_uid()`, `get_email_body()`, `reply_to_email()` utilisent `BODY.PEEK[]`.
- `tools/protonmail.py` : `_extract_text_body()` gère les emails HTML-only (sans `text/plain`).
- `agents/protonmail_agent.py` : `analyser_et_generer()` retourne `{priorite, contexte, option_courte, option_complete}`. Clés normalisées : `from` (et non `sender`), `snippet`/`body` (et non `preview`).
- `_executer_action` et `cmd_login_proton` utilisent le paramètre `email_addr=` (et non `email=`).
- `mark_as_read(uid)` appelé après `reply_to_email()`.
- Logging INFO activé pour le module `julien_os` — visible dans `journalctl -u julien-os`.
- `/forcer_proton` affiche un rapport détaillé : dossier scanné, priorité LLM, raison du skip.

Note opérationnelle : « 0 alerte envoyée » n'est pas un bug. Si tous les non-lus sont des notifications automatiques (Airbnb, GitHub, Anthropic), le watcher les classe `IGNORER` correctement.

## Prérequis Proton Bridge

- Bridge actif sur le VPS : `systemctl status proton-bridge`
- `bridge_password` dans `/root/secrets.json` → clé `protonmail.bridge_password`
- Test de connexion : `/forcer_proton` dans Telegram
