# ADR-004 — Playwright avec profil Chrome persistant pour Airbnb

**Date** : 2026-04-07
**Statut** : Accepté

## Contexte

Accès à Airbnb pour lire les messages voyageurs. Pas d'API officielle.

## Décision

Playwright avec `launch_persistent_context` + playwright-stealth.

## Raisons

- Seule méthode disponible (pas d'API officielle Airbnb)
- Profil Chrome persistant dans `.chrome_profile/airbnb/` — cookies survivent aux redémarrages
- Stealth mode réduit la détection bot

## Conséquences

- Browser ouvert uniquement pendant le scan (~30s), puis fermé → RAM libérée
- **Ne jamais tuer avec `pkill -9`** — cookies non flushés, session perdue
- Domaine cible : `https://www.airbnb.ca` (Canada)
- Session expire parfois malgré le profil persistant → `/login_airbnb` pour renouveler

## Pattern fermeture correcte

```python
@asynccontextmanager
async def _ctx():
    ctx = await pw.chromium.launch_persistent_context(user_data_dir=PROFILE_DIR)
    yield ctx
    await ctx.close()  # flush cookies sur disque
```
