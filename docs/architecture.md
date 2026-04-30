# Architecture — Julien OS

## Vue d'ensemble

```
Telegram (voix/texte)
        │
        ▼
   main.py (Bot)
        │
        ▼
   graph.py (LangGraph)
   ┌─────────────────────────────────────┐
   │  node_input → node_route →          │
   │  node_agent → node_save_memory →    │
   │  node_format → node_output          │
   └─────────────────────────────────────┘
        │                    │
        ▼                    ▼
   agents/              tools/
   (spécialisés)        (exécution)
        │                    │
        ▼                    ▼
   memoire.db           APIs externes
   (SQLite)             (Proton, Airbnb, Notion)
```

## Flux de traitement d'un message

1. **Réception** — `main.py` reçoit le message Telegram (texte ou vocal)
2. **Transcription** — Si vocal : `tools/transcription.py` (Whisper)
3. **Routage** — `graph.py::node_route` détecte l'agent cible via mots-clés
4. **Exécution** — L'agent spécialisé produit une réponse
5. **Mémoire** — `node_save_memory` stocke un résumé dans SQLite
6. **Formatage** — `tools/telegram_format.py` nettoie le markdown
7. **Envoi** — Réponse renvoyée dans Telegram

## Agents spécialisés

| Agent | Fichier | Déclencheur |
|-------|---------|-------------|
| Compte-rendu | `agents/cr.py` | `/cr`, mots-clés réunion |
| Email | `agents/email.py` | `/email`, mots-clés courriel |
| Shepherd | `agents/shepherd.py` | `/shepherd`, analyse projet |
| Mémoire | `agents/memoire.py` | `/memoire` |
| Préparation | `agents/prep.py` | `/prep` |
| Direct | `agents/direct.py` | Tout le reste |
| Consolidation | `agents/consolidation.py` | `/consolider` |
| Hebdo | `agents/hebdo.py` | Lundi 8h EDT (job_queue) |

## Watchers (arrière-plan asyncio)

Deux boucles indépendantes lancées dans `post_init` (actuellement en pause) :

```
demarrer_watcher() → loop toutes les 60 min
    └── poll_once()
        ├── get_unread_messages() → None si session expirée
        ├── Si None : marquer_alerte() + send_message()
        └── Si liste : analyser + créer pending + alerter
```

**Anti-doublon** : `watchers/flags.py` stocke les flags en SQLite
(`watcher_flags` table). Flag posé AVANT l'envoi pour survivre aux crashes.

## Mémoire

```
memoire.db
├── memoire          ← Résumés par projet (court/moyen terme)
├── alertes_custom   ← Alertes configurées par /alerte
├── pending_actions  ← Actions en attente de confirmation
├── watcher_flags    ← Flags anti-doublon pour les watchers
└── config           ← Configuration dynamique
```

## Intégration Notion

`tools/notion_tool.py` — notion-client v3 (async) :
- `creer_note(texte)` — nouvelle page dans la DB
- `lire_page(page_id)` — lecture d'une page
- `chercher(query)` — recherche full-text
- `ajouter_cr_ia(date, resume, plan)` — insère un CR dans le Tableau de bord

Insertion positionnelle via `after=BLOCK_ID` pour ordre newest-first.

## Sessions browser (Airbnb)

Profile Chrome persistant : `/root/julien_os/.chrome_profile/airbnb/`

Cycle de vie du browser :
```python
@asynccontextmanager
async def _ctx():
    ctx = await pw.chromium.launch_persistent_context(user_data_dir=PROFILE_DIR)
    yield ctx
    await ctx.close()  # fermeture propre = cookies flushés sur disque
```

⚠️ Ne jamais tuer avec `pkill -9` — les cookies ne sont pas sauvegardés.

## Variables d'environnement et secrets

Tout dans `/root/secrets.json` (chmod 600) :
```json
{
  "telegram_token": "...",
  "anthropic_api_key": "...",
  "openai_api_key": "...",
  "notion_token": "...",
  "protonmail": { "email": "...", "bridge_password": "..." },
  "airbnb": { "email": "...", "password": "..." }
}
```
