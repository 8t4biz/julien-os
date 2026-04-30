# ADR-003 — Proton Bridge IMAP plutôt que Playwright

**Date** : 2026-04-07
**Statut** : Accepté

## Contexte

Accès à Proton Mail pour lire et envoyer des emails.

## Décision

Proton Bridge 3.23.1 headless + IMAP/SMTP sur localhost.

## Raisons

- Playwright sur proton.me bloque avec CAPTCHA puzzle anti-bot
- Proton Bridge est l'approche officielle et fiable
- Zéro risque de ban
- Port IMAP : localhost:1143, SMTP : localhost:1025

## Conséquences

Proton Bridge doit tourner en service systemd sur le VPS. Bridge password distinct du mot de passe Proton Mail, stocké dans `secrets.json`.
