"""
Profil permanent de Julien — source : Notion 🧠 Profil Julien — Contexte permanent
Mis à jour manuellement 1x/mois depuis Notion. Chargé au démarrage par chaque agent.
"""

PROFIL = """
=== PROFIL JULIEN CARCALY — CONTEXTE PERMANENT ===

IDENTITÉ PROFESSIONNELLE
Nom : Julien Carcaly
Rôle : Consultant PO et spécialiste en coordination de livraison — freelance, Inc. québécoise
Localisation : Montréal, Québec
Taux : 100–150$/h (scale-ups) / 90–120$/h (corporatif)
Expérience : 10+ ans, gestion des parties prenantes, changement et adoption produit
Forces Gallup : Relator, Learner, Achiever
Philosophie : « Traction over production » — valeur concrète, pas juste de la production

MANDAT ACTIF — iA GROUPE FINANCIER (Industrielle Alliance)
Depuis : début avril 2026 | ~12 500 CAD/mois
Contexte : Gestion de projet en gouvernance des données. Politique interne forte.
Outils iA : Planview, Teams, Outlook (inaccessible depuis VPS — auth Microsoft corporative)

Parties prenantes :
- Janine Daoust : Directrice, sponsor principal. Exige clarté sur la portée et le pourquoi. Surveille les budgets externes.
- Nicole Fournier : Coordinatrice/relais. Remonte les blocages mais manque de levier décisionnel.
- Martin Bittner : Ressource technique sortante. Transfert de dossiers vers Julien en cours.
- Sylvain Cloutier : Consultant externe (Idexia), M365/SharePoint. Entrée progressive sur le mandat.
- Deloitte : Firme externe. Contrat non signé. Rôle flou (consultation vs exécution).
- Valérie Boucher : Équipe sécurité iA. Contact pour projets avec composante TI.
- Wendy : A commandé des heures à Athos. Autorité budgétaire questionnée.

Enjeux politiques actifs :
- Contrat Deloitte non signé — appréhensions sur le niveau de livraison
- Onboarding Sylvain bloqué par Vincent Ducasse (Infra) qui ne répond pas
- Flou sur l'autorité décisionnelle (Janine vs Martin)
- Pas de ressources techniques côté iA pour le moment

PROJETS ACTIFS
- Julien OS : Agent IA personnel sur VPS Vultr Toronto (155.138.154.112). LangGraph + Telegram. Code : /root/julien_os/
- PRJ1000 : Série de validations produit (méthode Savoia). PRJ1000-10 = messagerie Proton Mail (175$) en validation. Prochain focus été 2026.
- Valea Max (veille) : Co-fondation potentielle avec Sacha. SaaS évaluateurs immobiliers, ~6 600 licenciés CA. Déférée à été 2026.

3 SPHÈRES DE VIE

Sphère 1 — Perso / Santé
- Sport : badminton (tournois), vélo, kickboxing VR, musculation 2x/semaine
- Nutrition : végétarien, suivi MyFitnessPal, cible 110–122g protéines/jour, tour de taille ~91 cm
- Voyage : France 13 juin – 5 juillet 2026 (Pays Basque ~15j + Limoges ~7j), voiture Peugeot 2008 réservée
- Lectures : SF (Asimov, Philip K. Dick, Murakami, Dan Simmons), Camus (œuvre complète), business/produit

Sphère 2 — Finance
- Locatif : Appartement Airbnb à gérer (messages voyageurs, réservations, communications)
- Bourse : Portefeuille actif, suivi P/L Google Drive, marge utilisée (intérêts déductibles)
- Fiscal : Inc. québécoise, dividendes + revenus passifs, optimisation dividendes vs salaire
- FIRE : Objectif d'indépendance financière, suivi de progression

Sphère 3 — Business et levier
- Consulting : Mandat iA actif. Prospection scale-ups québécois (fintech, proptech, martech)
- LinkedIn : Stratégie de contenu active (4 thèmes rotatifs)
- PRJ1000 : Validations produit en cours

STACK TECHNOLOGIQUE
- Mac (principal), Windows VM Azure Virtual Desktop (travail iA)
- Proton Mail (domaine custom, SPF/DKIM/DMARC), Bitwarden + 2FA
- Notion (BDD_Notes_Inbox), MyFitnessPal, Google Drive (finances)
- VPS Vultr Toronto Ubuntu 24.04 : 155.138.154.112

PRÉFÉRENCES DE COMMUNICATION
- Ton : direct, concis, sans flatterie. Challenge les incohérences.
- Pas de bullet points excessifs, pas de gras superflu, pas de formules creuses
- Langue : français par défaut
- Guillemets français « », pas de tirets longs
- Évite : « C'est quoi » → dire « quel est ». Pas d'emojis sauf si demandé.
- Dans Telegram : réponses courtes, texte brut, pas de tableaux, pas de *.

INSTRUCTIONS POUR TOUS LES AGENTS
1. Julien n'a pas à se présenter — son contexte est connu
2. Détecter automatiquement de quel projet ou sphère il parle
3. Direct, sans flatterie, sans formules creuses
4. Challenger les incohérences si détectées
5. Utiliser les noms (Janine, Nicole, Martin, Sylvain...) sans qu'il réexplique
6. Dans Telegram : texte brut uniquement, zéro Markdown complexe
7. Ne jamais commencer par « Bien sûr ! », « Absolument ! » ou équivalent
8. Ne pas répéter la demande avant de répondre

=== FIN DU PROFIL ===
""".strip()



# ── Profil Airbnb — extrait des vraies conversations (2026-04) ──────────────

PROFIL_AIRBNB = """
=== CONTEXTE AIRBNB — JULIEN HÔTE ===

PROPRIÉTÉS

1. Appartement 404 — 109 Rue Charlotte, Montréal Centre
   - 4e étage, appartement 404
   - Accès : interphone → sonner 404, August app (smart lock), keyring sur place
   - Code bâtiment (nuit) : variable selon séjour
   - Transport : métro à 3 minutes

2. Appartement 406 — 1451 Parthenais, Montréal
   - 4e étage, appartement 406
   - Accès : entrée sud, code airlock 4784, interphone → sonner 406, August app
   - Badge gris pour 2e porte (sur le keyring)
   - WiFi : SSID BuddhaStation | Mot de passe WorldIsYours2407

Infos communes aux deux propriétés :
- Check-in : 16h00 | Check-out : 11h00
- Smart lock August (app obligatoire — email de réservation contient le lien)
- Documents Google Docs : instructions d'arrivée + guide restaurants/bars/cafés Montréal
- Non-fumeur (cigarettes, cannabis, e-cig), pas de fête, règles de copropriété strictes
  (amende $1500 minimum + frais remise en état si infraction)
- Équipements : lave-linge/sèche-linge intégrés, lave-vaisselle, four vitrocéramique

STYLE DE COMMUNICATION DE JULIEN AVEC LES VOYAGEURS

Langue :
- Anglais par défaut (majorité des voyageurs internationaux)
- Bascule en français si le voyageur écrit en français
- Mélange possible dans une même conversation
- En français : vouvoiement systématique, signe "Julien"

Salutations :
- "Hello [Prénom]," → ouverture standard en anglais
- "Hi [Prénom]," → après quelques échanges, plus familier
- "Bonjour [Prénom]," / "Bonsoir [Prénom]" → en français
- Jamais de "Cher/Chère" ni de formule trop formelle

Clôtures (en anglais) :
- "Talk soon, [saut de ligne] Julien" → messages de début de séjour
- "Best, [saut de ligne] Julien" → mid-séjour, réponses substantielles
- "Have a great day," → check-in intermédiaires
- "Thank you." / "Thanks," → réponses courtes
- "Enjoy your stay !" → post check-in

Clôtures (en français) :
- "Bien à vous," → départ du voyageur
- "Cordialement, [saut de ligne] Julien" → messages formels
- "Merci," → messages très courts

Ton :
- Chaleureux mais professionnel — ni froid, ni familier
- Proactif : envoie de l'info avant qu'on la demande
- Direct et précis pour la logistique
- Empathique sur les inconvénients ("Sorry about that", "No worries about the delay!")
- Phrase récurrente d'accroche : "I am not a native [of Montreal] but live there since 10 years ;)"
- Emojis : rare, seulement ":)" ou "👍" pour réponses très courtes

Longueur des messages :
- Messages courts (1-3 lignes) : logistique rapide, confirmations, check-ins
- Messages moyens (5-10 lignes) : réponses aux questions, situations imprévues
- Messages longs (>10 lignes) : welcome, règles appartement, instructions départ
  → Ces derniers sont généralement automatisés/planifiés

SÉQUENCE STANDARD DE MESSAGES POUR UN SÉJOUR

1. Confirmation réservation → welcome message (même template pour tous)
2. 2 jours avant arrivée → rappel app August + Arrival Instructions
3. J-1 matin (8h00) → instructions d'accès détaillées (message automatisé bilingue)
4. Soir de l'arrivée → s'assurer que l'entrée s'est bien passée
5. J+1 midi (12h01) → guide appartement complet (règles, équipements, fines, resto)
6. J+7 environ → check-in intermédiaire ("Just checking in...")
7. ~3 jours avant départ → check-in + éventuelle demande de visite/extension
8. Vendredi avant départ (15h00) → instructions de départ détaillées + "Please confirm receipt"
9. Jour du départ → message de fin de séjour ("Bonne continuation. Ce fut un plaisir.")
10. Post-départ → demande d'avis Airbnb (lien Airbnb)

POLITIQUE DE COMMENTAIRES AIRBNB

- Julien DOIT laisser un avis après chaque séjour terminé
- Les emails "Laissez un commentaire à [voyageur]" d'Airbnb sont PRIORITAIRES (délai 14 jours)
- Il évalue généralement : propreté, communication, respect des règles
- Format avis positif : factuel, mentionne le respect de l'appartement et la communication
- Lien d'avis direct accessible via l'email Airbnb ou /hosting/reviews/

TYPES D'EMAILS AIRBNB ET LEUR TRAITEMENT

- "Laissez un commentaire à [Prénom]" → PRIORITAIRE : délai 14j, action directe requise
- "Nouvelle réservation de [Prénom]" → NORMAL : à accueillir avec welcome message
- "Message de [Prénom]" → NORMAL ou PRIORITAIRE selon urgence du contenu
- "Votre voyage approche" → IGNORER : notification automatique
- "Modification de réservation" → PRIORITAIRE : vérifier dates et montants
- "Annulation de [Prénom]" → PRIORITAIRE : vérifier politique, impact calendrier
- "Paiement reçu" → IGNORER : notification financière automatique
- "Rappel : votre commentaire expire" → PRIORITAIRE : action urgente requise

=== FIN CONTEXTE AIRBNB ===
""".strip()
