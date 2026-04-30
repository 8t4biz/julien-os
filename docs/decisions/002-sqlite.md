# ADR-002 — SQLite comme base de données principale

**Date** : 2026-04-06
**Statut** : Accepté — migration PostgreSQL prévue Phase 2

## Contexte

Besoin de persistance pour la mémoire, les alertes, les actions en attente.

## Décision

SQLite (`/root/memoire.db`).

## Raisons

- Simple, local, zéro infrastructure supplémentaire
- Suffisant pour un usage mono-utilisateur
- Migration PostgreSQL possible en Phase 2 sans changer l'interface

## Conséquences

Fichier unique sur le VPS. Tables : `memoire`, `alertes_custom`, `pending_actions`, `watcher_flags`, `config`.
