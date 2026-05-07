# ADR-007 — Profil Airbnb enrichi depuis conversations Playwright

**Date** : 2026-04-26
**Statut** : Adopté

## Contexte

L'agent Airbnb générait des réponses génériques sans connaître les propriétés de Julien, leurs codes d'accès, ni le ton qu'il utilise habituellement avec les voyageurs. Les options proposées tombaient à côté en français comme en anglais.

## Décision

Extraire les données réelles depuis 4 conversations consultées via Playwright sur airbnb.ca/hosting/messages (Zohra/Alexandre, Cheryl, Mouhannad, Nebal/Nawras Ahmad), puis les encoder dans `profil.py` (constante `PROFIL_AIRBNB`) et spécialiser le prompt de `protonmail_agent` pour les emails Airbnb.

### Données extraites

Deux propriétés actives :
- 404-109 Rue Charlotte (Montréal Centre, 4e étage, métro 3 mn)
- 406-1451 Parthenais (4e étage, code airlock 4784)
- Check-in 16h00 / Check-out 11h00 sur les deux
- Smart lock August, keyring sur place

Style de communication :
- Anglais dominant, bascule en français si le voyageur écrit en français
- Vouvoiement en français, signe « Julien »
- Salutation : « Hello [Prénom], » | clôture : « Talk soon, » puis « Best, » puis « Bien à vous, »
- Proactif, chaleureux, précis sur la logistique
- Pas d'emojis sauf « :) » occasionnel

Politique de commentaires :
- Emails « Laissez un commentaire à [Prénom] » → PRIORITAIRE (délai 14 jours)
- Options générées = textes d'avis prêts à poster, rédigés en français

## Raisons

- Les conversations réelles donnent une fidélité de ton impossible à inventer.
- Les deux propriétés ont des codes et spécificités logistiques différents : un prompt générique se trompait régulièrement.
- La politique avis (délai 14 j) doit déclencher une priorité haute pour ne pas rater la fenêtre.

## Conséquences

- `/root/julien_os/profil.py` : ajout de `PROFIL_AIRBNB` (2 propriétés, style, séquence messages, politique avis).
- `/root/julien_os/agents/protonmail_agent.py` : prompt spécialisé Airbnb, détection automatique via `_est_email_airbnb()`, icône maison dans l'alerte Telegram.
