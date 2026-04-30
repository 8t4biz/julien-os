# Julien OS — Mémoire projet pour Claude Code

> Ce fichier est lu par Claude Code à chaque session. Il contient tout le contexte nécessaire pour reprendre le travail sans réexpliquer.

---

## Qui est Julien

Julien Carcaly, consultant PO freelance à Montréal, Inc. québécoise. Mandat actif chez iA Groupe financier (~12 500$/mois). Pas développeur — Claude Code écrit et déploie tout le code.

## Ce qu'est ce projet

Julien OS est un agent personnel IA guidé par la voix via Telegram, tournant 24/7 sur un VPS Vultr Toronto. Il orchestre plusieurs agents spécialisés pour les 3 sphères de vie de Julien : Business/Consulting, Finance, Perso.

**Principe fondateur :** Julien délègue l'exécution. L'agent exécute. Julien garde les décisions.

---

## Infrastructure

- **VPS** : Vultr Toronto, 155.138.154.112, Ubuntu 24.04
- **Connexion** : `ssh root@155.138.154.112` (SSH sans mot de passe configuré)
- **Code** : `/root/julien_os/` (architecture LangGraph modulaire)
- **Lancer le bot** : `pkill -9 -f julien_os && sleep 3 && cd /root && nohup python3 -m julien_os.main > /root/julien_os.log 2>&1 &`
- **Logs** : `tail -f /root/julien_os.log`
- **DB** : `/root/memoire.db` (SQLite)
- **Secrets** : `/root/secrets.json` (Proton Mail, Airbnb, Notion token)
- **Profil Julien** : `/root/julien_os/profil.py`

---

## Structure du code

```
/root/julien_os/
├── main.py              ← Bot Telegram (entry point)
├── graph.py             ← Orchestrateur LangGraph (7 nœuds)
├── state.py             ← AgentState
├── profil.py            ← Contexte permanent de Julien
├── agents/
│   ├── cr.py            ← Compte-rendu transcriptions
│   ├── email.py         ← Rédaction emails
│   ├── shepherd.py      ← Analyse projet (Project Shepherd)
│   ├── memoire.py       ← Mémoire persistante
│   ├── prep.py          ← Préparation réunion
│   ├── direct.py        ← Réponse directe
│   ├── consolidation.py ← /consolider — résumé 90 jours
│   └── hebdo.py         ← Tableau de bord lundi 8h EDT
├── memory/
│   └── store.py         ← SQLite helpers
├── tools/
│   ├── transcription.py ← Whisper (OpenAI)
│   ├── protonmail.py    ← Proton Bridge IMAP/SMTP
│   ├── airbnb_scraper.py← Playwright stealth
│   ├── notion_tool.py   ← Notion API
│   └── telegram_format.py ← Filtre formatage HTML
├── watchers/
│   ├── protonmail_watcher.py ← Polling Proton (60 min, EN PAUSE)
│   ├── airbnb_watcher.py    ← Polling Airbnb (60 min, EN PAUSE)
│   └── flags.py             ← Flags persistants SQLite (anti-doublon)
└── docs/
    ├── architecture.md  ← Architecture détaillée
    └── decisions/       ← ADR — Architecture Decision Records
```

---

## Stack technique

| Couche | Technologie |
|--------|------------|
| Orchestration | LangGraph v1.1.6 |
| LLM | Claude Opus via Anthropic API |
| Voix | OpenAI Whisper |
| Email | Proton Bridge 3.23.1 (IMAP localhost:1143) |
| Browser | Playwright + playwright-stealth (Airbnb) |
| DB | SQLite (`/root/memoire.db`) |
| Bot | python-telegram-bot |
| Notion | notion-client 3.x (async) |

---

## Commandes Telegram actives

`/cr` `/email` `/shepherd` `/prep` `/memoire` `/projets` `/consolider` `/stats` `/alerte` `/mails` `/forcer_proton` `/forcer_airbnb` `/login_airbnb` `/login_proton` `/surveillance` `/noter` `/aide`

---

## État — 2026-04-22 (retour congés appliqué)

### ✅ Fait le 2026-04-22
1. Tests de régression — **27/27 OK** sur tous les agents
2. Monitoring + restart automatique — **systemd `julien-os.service`** (Restart=always, enabled)
3. Watchers Proton et Airbnb réactivés — **batch 2x/jour à 11h45 EDT (15h45 UTC) et 17h EDT (21h UTC)**
   - Jobs : `proton_batch_matin`, `proton_batch_soir`, `airbnb_batch_matin`, `airbnb_batch_soir`
   - Notification Telegram à chaque démarrage/restart du bot

### À faire (non traité)
- Upgrade VPS à 2 GB RAM sur Vultr (10$/mois)
- Répondre ticket Vultr SXL-80AMX

### Problèmes connus (toujours actifs)
- Session Airbnb expire après quelques heures malgré stealth mode → `/login_airbnb` si nécessaire
- Notifications Proton arrivent sans résumé ni vraies options de réponse

### Commandes utiles
- Voir statut : `systemctl status julien-os`
- Relancer : `systemctl restart julien-os`
- Logs en direct : `journalctl -u julien-os -f`
- Tests régression : `cd /root && python3 julien_os/tests/test_regression.py`

---

## Notion

- Page pilotage : https://www.notion.so/33afc1ded4cc8171ae20c0aa83ce2c78
- Profil Julien : https://www.notion.so/33cfc1ded4cc81f0ab88cc8b5c88cc75
- Tableau de bord : https://www.notion.so/33cfc1ded4cc818da2bbf542a4bcec0e

---

## Règles importantes

- Julien n'est pas développeur — expliquer ce que tu fais, pas comment
- Toujours vérifier `tail -20 /root/julien_os.log` après un redémarrage
- Ne jamais modifier `secrets.json` sans confirmer avec Julien
- Mettre à jour ce fichier CLAUDE.md après chaque session significative
- Toujours lire la page Notion pilotage au début d'une nouvelle session
- Les flags watcher sont en SQLite (`watcher_flags` table dans `memoire.db`)
- `marquer_alerte()` toujours AVANT `bot.send_message()` pour éviter les doublons

---

## Flux Proton Mail — état 2026-04-26

### Architecture bout-en-bout (livré et opérationnel)

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
  → Telegram : ✅ Envoyé
```

### Bugs corrigés (2026-04-26)
| Bug | Fix |
|-----|-----|
| Clé `sender` → `from` | protonmail_agent.py L.51 |
| Clé `preview` → `snippet`/`body` | watcher charge body complet pour tous |
| Regex fragile options | Remplacé par JSON structuré — 1 seul appel LLM |
| Options tronquées 150 chars | formater_alerte_telegram : affichage complet |
| 2 appels LLM séparés | analyser_et_generer() — 1 seul appel |
| `email=` au lieu de `email_addr=` | _executer_action + cmd_login_proton |
| Email reste non-lu après réponse | mark_as_read(uid) après reply_to_email |
| Corps NORMAL non chargé | Tous les emails chargés en full body |


### Bug critique corrigé — 2026-04-26
**`FETCH (RFC822)` marquait les emails comme lus (`\Seen`) à chaque scan.**
Résultat : au premier scan, l'email était détecté mais immédiatement marqué lu.
Au scan suivant, SEARCH UNSEEN retournait vide → détection perpétuellement 0.

**Fix : `FETCH (BODY.PEEK[])` — identique à RFC822 mais préserve le flag `\Seen`.**
Appliqué dans `get_unread_emails()`, `get_email_body_by_uid()`, `get_email_body()`, `reply_to_email()`.
`mark_as_read(uid)` est maintenant le seul endroit où `\Seen` est posé (après envoi réel).

Fix secondaire : `_extract_text_body()` gère maintenant les emails HTML-only (sans `text/plain`).

### Debug multi-dossiers — 2026-04-26
**Problème réel :** le watcher ne scannait que INBOX. Les emails de Julien sont dans des sous-dossiers ProtonMail.

**Fix :** `FOLDERS_TO_SCAN` dans `ProtonMailClient` — scan multi-dossiers avec déduplication par Message-ID :
- INBOX
- Folders/[INC] Consulting
- Folders/[INC] Build
- Folders/[INC] Finance
- Folders/[FI]
- Folders/[PERSO]

**Logging INFO activé** pour le module `julien_os` — visible dans `journalctl -u julien-os`.

**`/forcer_proton` affiche maintenant un rapport détaillé** : dossier scanné, priorité LLM, raison du skip.

**Note :** "0 alerte envoyée" ≠ "bug". Si tous les non-lus sont des notifications auto (Airbnb, GitHub, Anthropic), le watcher les classe IGNORER correctement.

### Proton Bridge — prérequis
- Bridge doit tourner sur le VPS : `systemctl status proton-bridge`
- `bridge_password` dans `/root/secrets.json` → clé `protonmail.bridge_password`
- Tester la connexion : `/forcer_proton` dans Telegram


---

## Profil Airbnb — enrichissement 2026-04-26

### Données extraites depuis les vraies conversations Playwright

Via airbnb.ca/hosting/messages — 4 conversations lues (Zohra/Alexandre, Cheryl, Mouhannad, Nebal/Nawras Ahmad).

**Deux propriétés actives :**
- 404-109 Rue Charlotte (Montréal Centre, 4e étage, métro 3mn)
- 406-1451 Parthenais (4e étage, code airlock 4784)
- Check-in 16h00 / Check-out 11h00 sur les deux
- Smart lock August, keyring sur place

**Style de communication analysé :**
- Anglais dominant, bascule en français si le voyageur écrit en français
- Vouvoiement en français, signe "Julien"
- Salutation : "Hello [Prenom]," | Cloture : "Talk soon," puis "Best," puis "Bien a vous,"
- Proactif, chaleureux, precis sur la logistique
- Pas d'emojis sauf ":)" occasionnel

**Fichiers modifies :**
- /root/julien_os/profil.py -> ajout PROFIL_AIRBNB (2 proprietes, style, sequence messages, politique avis)
- /root/julien_os/agents/protonmail_agent.py -> prompt specialise Airbnb, detection auto _est_email_airbnb(), icone maison dans Telegram

**Politique de commentaires Airbnb :**
- Emails "Laissez un commentaire a [Prenom]" -> PRIORITAIRE (delai 14j)
- Options generees = textes d'avis prets a poster, rediges en francais


## Rappel pending + commande /pending — 2026-04-26

### Logique rappel (job_rappel_pending)
- Job run_repeating toutes les 3600s (premier check 5 min apres demarrage)
- Cherche les pending en_attente depuis plus de 4h sans reponse de Julien
- Condition : created_at < now-4h ET (dernier_rappel_at IS NULL OU dernier_rappel_at < now-4h)
- Renvoie l alerte originale avec prefixe RAPPEL (Xh sans reponse) + les 2 options + ID
- Met a jour dernier_rappel_at apres envoi -> pas de re-rappel avant 4h supplementaires
- Colonne dernier_rappel_at ajoutee a pending_actions (migration douce ALTER TABLE)

### Commande /pending
- Liste tous les pending statut=en_attente non expires
- Affiche : [ID] SOURCE - age | De : ... | Sujet : ...
- Tri du plus recent au plus ancien

### Fichiers modifies
- /root/julien_os/memory/pending.py : +get_tous_pending_actifs(), +get_pending_a_rappeler(), +marquer_rappel_envoye()
- /root/julien_os/main.py : +cmd_pending, +job_rappel_pending, run_repeating 3600s, CommandHandler pending


## Flux réponse email complet — 2026-04-26

### _executer_action — branchement Airbnb vs SMTP

La fonction _executer_action(state, bot=None, chat_id=None) distingue maintenant deux chemins :

Chemin Airbnb (source=protonmail + expediteur contient "airbnb") :
- Pas de SMTP (adresses no-reply@airbnb.com, automated@airbnb.com, etc.)
- Si demande d'avis (sujet contient commentaire/review/avis/laisser) → envoie lien Airbnb reviews
- Sinon → message informatif "Email Airbnb traite"
- Retourne True (succes) sans appel SMTP

Chemin email normal (source=protonmail, expediteur non-Airbnb) :
- folder = item_data.get("folder") or "INBOX" — protege contre folder=None dans les anciens pendings
- Appel SMTP via ProtonMailClient.reply_to_email()
- Log INFO avec resultat OK/ECHEC + folder + uid

Chemin Airbnb natif (source=airbnb) :
- Playwright AirbnbClient → send_message() via interface web

### Orphan recovery au demarrage (post_init)

Au redemarrage du bot, le dict _en_attente_confirmation (in-memory) est vide.
Si un pending avait statut=confirme + reponse_choisie non-nulle → confirmation perdue.

Fix : post_init appelle get_pending_confirme_orphelin() → si orphelin trouve :
1. Recharge dans _en_attente_confirmation[chat_id]
2. Envoie alerte Telegram : texte + "Reponds OUI pour envoyer, NON pour annuler"

Fonction get_pending_confirme_orphelin() dans pending.py :
- WHERE statut='confirme' AND reponse_choisie IS NOT NULL
- ORDER BY created_at DESC LIMIT 1

### Tests bout-en-bout reussis (2026-04-26)

| Test | Source | Resultat |
|------|--------|---------|
| Communauto (uid=1, INBOX) | protonmail | SMTP OK, email marque lu |
| Zohra review (automated@airbnb.com) | protonmail | Informationnel, lien reviews envoye |

Logs VPS confirmes :
- reponse envoyee a "Communauto Quebec" noreply@communauto.com
- email UID=1 marque comme lu
- _executer_action: SMTP reply OK folder=INBOX uid=1
- _executer_action: email Airbnb dans Proton — action informative, pas de SMTP

### Fichiers modifies
- /root/julien_os/main.py : _executer_action Airbnb branch + signature bot/chat_id + orphan recovery post_init
- /root/julien_os/memory/pending.py : +get_pending_confirme_orphelin()


## Corrections flux pending — 2026-04-26 (session 2)

### Fix 1 : Détection no-reply avant SMTP

_executer_action vérifie maintenant l'adresse expéditeur AVANT d'appeler SMTP.
Si l'adresse contient : noreply, no-reply, automated, do-not-reply, donotreply, do_not_reply → SMTP bloqué.

Comportement :
- Airbnb review (automated@ + sujet "commentaire/review/avis/laisser") → "Texte prêt + lien Airbnb reviews"
- Autre no-reply → "⛔ Envoi bloqué : [adresse] est une adresse no-reply"
- Email normal (Clinique dentaire, consultant, etc.) → SMTP Proton Bridge comme avant

Fichier modifié : /root/julien_os/main.py — _executer_action(), remplacement du bloc est_airbnb par NOREPLY_PATTERNS

### Fix 2 : drop_pending_updates=True au démarrage du bot

Problème : à chaque restart du bot, Telegram rejouait les anciens messages (ex. "3" ou "NON" envoyés pendant les tests).
Ces messages relancaient handle_validation() et appelaient ignorer_pending() sur ID=2 sans que Julien le veuille.

Fix : app.run_polling(drop_pending_updates=True)
→ Au démarrage, le bot ignore tous les messages arrivés pendant son absence.
→ Julien doit renvoyer un message pour interagir après un restart.

### Fix 3 : expires_at retiré de get_pending_actif() et get_tous_pending_actifs()

Un pending en_attente reste visible dans /pending ET répondable (1/2/3) indéfiniment.
Il disparaît uniquement quand Julien répond : OUI → envoye, NON/3 → ignore.
expires_at est conservé uniquement dans get_pending_a_rappeler() (pas de rappel automatique pour les vieux emails).

### État DB après corrections
- ID=1 (Clinique dentaire, uid=6, INBOX) : en_attente — chemin SMTP
- ID=2 (Zohra Airbnb review, uid=5, INBOX) : en_attente — chemin no-reply (bloqué)
- ID=3 (Communauto) : envoye — déjà traité


## Fix UID rafraîchi pour pending existants — 2026-04-27

### Problème
Quand ProtonMail réorganise sa boîte (déplacement, archivage, change de label), un email garde son Message-ID mais reçoit un nouvel UID IMAP. Conséquences avant fix :
- Le watcher détectait correctement le doublon via Message-ID (`item_deja_traite=True`)
- Mais l'item_data du pending existant gardait l'ancien UID (uid=5 alors que l'email était à uid=4)
- Si Julien validait OUI sur ce pending, `mark_as_read(uid="5")` ciblait un UID inexistant ou un autre email
- Le rapport `/forcer_proton` disait juste « ⏭ déjà traité » sans pointer vers le pending concerné — Julien ne savait pas où retrouver l'email dans `/pending`

### Fix appliqué

1. **`memory/pending.py`** — nouvelles fonctions :
   - `get_pending_by_item_id(source, item_id)` : retourne le dernier pending pour un Message-ID
   - `update_pending_item_data(pending_id, item_data)` : met à jour le JSON item_data

2. **`watchers/protonmail_watcher.py`** — quand `item_deja_traite=True` :
   - Charge le pending existant
   - Si statut=en_attente ET (uid ou folder a changé) : rafraîchit `item_data.uid` et `item_data.folder` avec les valeurs courantes
   - Rapport explicite : `🔄 pending #X — UID rafraîchi 5→4` ou `⏭ déjà traité — pending #X (en_attente)`

3. **`main.py` — cmd_pending** : affiche maintenant la référence `folder#uid` à côté de l'âge, ex. `[2] PROTONMAIL — 19h03 INBOX#4`. Permet à Julien de vérifier d'un coup d'œil que l'UID stocké correspond bien à l'email actuel.

### État DB après fix (2026-04-27 14:56 UTC)
- ID=1 (Clinique dentaire, uid=6, INBOX) : en_attente
- ID=2 (Zohra Airbnb review, **uid=4**, INBOX) : en_attente — UID rafraîchi de 5→4
- ID=3 (Communauto) : envoye
