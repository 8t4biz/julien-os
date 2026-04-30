# ADR-001 — LangGraph plutôt que CrewAI ou AutoGen

**Date** : 2026-04-07
**Statut** : Accepté

## Contexte

Besoin d'un framework d'orchestration multi-agents pour Julien OS.

## Décision

LangGraph (open source, gratuit) pour l'orchestration.

## Raisons

- Plus solide que CrewAI pour des workflows complexes et une architecture longue durée
- AutoGen est conçu pour la collaboration entre agents en mode itératif — moins adapté à un usage personnel temps réel
- Ratio effort vs bénéfice : 1 pour 5-10 en faveur LangGraph pour les agents autonomes avec initiatives
- Zéro coût additionnel

## Conséquences

Architecture modulaire dans `graph.py` avec 7 nœuds. Monitoring via LangSmith (plan gratuit).
