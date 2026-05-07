# Julien OS — Mémoire projet pour Claude Code

> Ce fichier est lu par Claude Code à chaque session. Il contient la référence statique du projet : qui, quoi, où, comment travailler. L'historique des décisions vit dans `docs/decisions/`.

---

## Qui est Julien

Julien Carcaly, consultant PO freelance à Montréal, Inc. québécoise. Mandat actif chez iA Groupe financier (~12 500 $/mois). Pas développeur — Claude Code écrit et déploie tout le code.

## Ce qu'est ce projet

Julien OS est un agent personnel IA guidé par la voix via Telegram, tournant 24/7 sur un VPS Vultr Toronto. Il orchestre plusieurs agents spécialisés pour les 3 sphères de vie de Julien : Business/Consulting, Finance, Perso.

**Principe fondateur :** Julien délègue l'exécution. L'agent exécute. Julien garde les décisions.

---

## Infrastructure

- **VPS** : Vultr Toronto, 155.138.154.112, Ubuntu 24.04
- **Connexion** : `ssh root@155.138.154.112` (SSH sans mot de passe configuré)
- **Code prod** : `/root/julien_os/`
- **Service** : `systemctl status|restart|stop julien-os` (`julien-os.service`, Restart=always, enabled)
- **Logs applicatifs** : `tail -f /root/julien_os.log`
- **Logs systemd** : `journalctl -u julien-os -f`
- **DB** : `/root/memoire.db` (SQLite)
- **Secrets** : `/root/secrets.json` (Proton Mail, Airbnb, Notion)
- **Profil Julien** : `/root/julien_os/profil.py`

### Lancer le bot manuellement (hors systemd)

```
pkill -9 -f julien_os && sleep 3 && cd /root && nohup python3 -m julien_os.main > /root/julien_os.log 2>&1 &
```

### Watchers programmés

- Proton Mail — batch 11h45 EDT (15h45 UTC) et 17h EDT (21h UTC)
- Airbnb — batch 11h45 EDT et 17h EDT
- Tableau de bord hebdo — lundi 8h EDT

### Tests de régression sur le VPS

```
cd /root && python3 julien_os/tests/test_regression.py
```

---

## Workflow de développement

- **Repo local** : `~/Projects/julien-os` (cloné depuis `git@github.com:8t4biz/julien-os.git`)
- **Venv local** : `.venv/` (Python 3.12 via Homebrew)
- **Pre-commit hooks installés** : ruff (`--fix`), detect-secrets, hooks de base (trailing-whitespace, end-of-file-fixer, check-yaml/json/toml, large-files, merge-conflict, private-key)
- **Configuration ruff** : `pyproject.toml` (line-length 100, py312, règles E/F/W/I/B/UP)
- **Git config** : Julien Carcaly `<apps@8t4.biz>`

### Cycle standard

1. Éditer en local (`~/Projects/julien-os`)
2. `pytest` si applicable (tests dans `tests/`)
3. `git add` les fichiers concernés
4. `git commit` — pre-commit s'exécute automatiquement
5. `git push origin main`
6. `ssh root@155.138.154.112 'cd /root/julien_os && git pull origin main && systemctl restart julien-os'`
7. Vérifier `tail -20 /root/julien_os.log` après le restart

Jamais `--no-verify` sauf cas explicite documenté.

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
│   ├── hebdo.py         ← Tableau de bord lundi 8h EDT
│   ├── conversational.py← Agent conversationnel V1.0.3.1
│   ├── airbnb_agent.py  ← Analyse messages Airbnb
│   └── protonmail_agent.py ← Analyse + génération options Proton
├── memory/
│   ├── store.py         ← SQLite helpers
│   ├── pending.py       ← Pending actions (réponses en attente OUI/NON)
│   ├── conversation.py  ← Sessions conversationnelles
│   └── scan_state.py    ← État des scans watcher
├── tools/
│   ├── transcription.py ← Whisper (OpenAI)
│   ├── protonmail.py    ← Proton Bridge IMAP/SMTP
│   ├── airbnb_scraper.py← Playwright stealth
│   ├── notion_tool.py   ← Notion API
│   ├── imap_actions.py  ← Helpers IMAP (move, mark_and_move)
│   ├── playwright_base.py
│   └── email_tools.py
├── watchers/
│   ├── protonmail_watcher.py ← Polling Proton (batch 2x/jour)
│   ├── airbnb_watcher.py     ← Polling Airbnb (batch 2x/jour)
│   └── flags.py              ← Flags persistants SQLite (anti-doublon)
├── telegram/
│   └── formatting.py    ← Filtre formatage HTML Telegram
└── docs/
    ├── architecture.md  ← Architecture détaillée
    └── decisions/       ← ADR — Architecture Decision Records
```

---

## Stack technique

| Couche | Technologie |
|--------|------------|
| Langage | Python 3.12 |
| Orchestration | LangGraph v1.1.6 |
| LLM | Claude Opus via Anthropic API |
| Voix | OpenAI Whisper |
| Email | Proton Bridge 3.23.1 (IMAP localhost:1143) |
| Browser | Playwright + playwright-stealth (Airbnb) |
| DB | SQLite (`/root/memoire.db`) |
| Bot | python-telegram-bot |
| Notion | notion-client 3.x (async) |
| Lint/Format | ruff (via pre-commit) |
| Sécurité | detect-secrets (baseline `.secrets.baseline`) |

---

## Commandes Telegram actives

`/cr` `/email` `/shepherd` `/prep` `/memoire` `/projets` `/consolider` `/stats` `/alerte` `/mails` `/forcer_proton` `/forcer_airbnb` `/login_airbnb` `/login_proton` `/surveillance` `/noter` `/pending` `/synthese` `/aide`

---

## Notion

- Page pilotage : https://www.notion.so/33afc1ded4cc8171ae20c0aa83ce2c78
- Profil Julien : https://www.notion.so/33cfc1ded4cc81f0ab88cc8b5c88cc75
- Tableau de bord : https://www.notion.so/33cfc1ded4cc818da2bbf542a4bcec0e

---

## Problèmes connus

- Session Airbnb expire après quelques heures malgré le stealth mode → `/login_airbnb` si nécessaire
- Notifications Proton arrivent sans résumé ni vraies options de réponse dans certains cas

## À faire (non urgent)

- Upgrade VPS à 2 GB RAM sur Vultr (10 $/mois)
- Répondre ticket Vultr SXL-80AMX

---

## Règles importantes

- Julien n'est pas développeur — expliquer ce que tu fais, pas comment
- Toujours vérifier `tail -20 /root/julien_os.log` après un redémarrage
- Ne jamais modifier `secrets.json` sans confirmer avec Julien
- Documenter chaque décision significative dans `docs/decisions/NNN-titre-court.md` (incrément séquentiel). Mettre à jour CLAUDE.md uniquement si la référence statique change : architecture, stack, workflow, infrastructure.
- Toujours lire la page Notion pilotage au début d'une nouvelle session
- Les flags watcher sont en SQLite (`watcher_flags` table dans `memoire.db`)
- `marquer_alerte()` toujours AVANT `bot.send_message()` pour éviter les doublons

---

## Décisions architecturales

Voir `docs/decisions/` pour l'historique complet des décisions (ADR-001 à ADR-NNN).
