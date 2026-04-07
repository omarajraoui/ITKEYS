# Job Apply Tool — Instructions Claude

Ce projet génère des CV + lettres de motivation + fiches de préparation adaptés à chaque offre d'emploi pour **Omar Ajraoui**.

## Architecture

```
mass/
├── data/
│   ├── truth.json           # Source de vérité (profil, expériences, bullets)
│   ├── latest_inspo.json    # Dernier JSON généré (analysis + bullets + lettre)
│   ├── scan_results.json    # Résultats du dernier scan d'offres
│   └── applications.db      # SQLite tracker
├── templates/
│   ├── cv_master.tex        # Template LaTeX CV (<<placeholders>>)
│   └── letter_master.tex    # Template LaTeX lettre (style français, fontawesome, teal)
├── src/
│   ├── adapter/             # (ancien, remplacé par Claude direct)
│   ├── compiler/            # Compilation LaTeX → PDF
│   ├── scraper/             # Scraping WTTJ (Algolia), France Travail, Indeed
│   └── tracker.py           # SQLite CRUD
├── compile_from_json.py     # Compile PDFs depuis latest_inspo.json
├── scan_jobs.py             # Lance le scan multi-source
└── output/                  # PDFs générés par entreprise/date
```

## Workflow principal

### Option A : L'utilisateur colle une offre
1. Analyser l'offre (track, keywords, tone, seniority)
2. Lire `data/truth.json` et adapter les bullets
3. Générer le summary adapté, la lettre de motivation
4. Écrire `data/latest_inspo.json`
5. Compiler les PDFs via `./gen`
6. Fournir la fiche de préparation dans le chat

### Option B : Scan automatique
1. Lancer `python scan_jobs.py` pour scanner WTTJ + France Travail + Indeed
2. Résultats dans `data/scan_results.json`
3. Claude analyse chaque offre pertinente et génère les candidatures

---

## Détail du workflow quand on traite une offre

### 1. Analyser l'offre
Déterminer :
- **track** : "tech" ou "consulting"
- **keywords** : technologies/compétences clés demandées
- **seniority** : junior / mid / senior
- **tone** : startup / esn / grand_groupe / cabinet_conseil
- **title_suggestion** : titre adapté pour le CV (PAS le titre exact de l'offre — voir règles)
- **company_name** : nom nettoyé de l'entreprise (sans "(ex-...)", "(anciennement ...)")

### 2. Écrire le summary adapté
Le summary affiché en haut du CV doit être **réécrit pour chaque offre**. Pas de texte générique.

Règles du summary :
- 2-3 phrases max
- Mentionner 1-2 technos ou domaines clés de l'offre nommément
- Mentionner les JO Paris 2024 si l'offre valorise les projets d'envergure ou la criticité
- Adapter le registre : tech = réalisations concrètes, consulting = posture et méthodes
- NE PAS dire "3 ans d'expérience" ou toute mention d'un nombre d'années

Exemples selon le type d'offre :
- DevOps/Cloud → "Ingénieur logiciel spécialisé DevOps et Cloud, ayant orchestré des déploiements Kubernetes critiques pour les JO Paris 2024. À l'aise sur l'ensemble de la chaîne CI/CD, de l'infrastructure as code à l'observabilité en production."
- Java/Backend → "Développeur backend Java Spring Boot ayant conçu et livré des microservices critiques dans le cadre des JO Paris 2024. Expérience bancaire (BNDE) et missions freelance sur des plateformes d'intégration d'entreprise."
- IA/GenAI → "Ingénieur logiciel ayant intégré des solutions IA Générative en production (RAG, LLM, PageIndex) dans le cadre de missions freelance. Expérience sur des systèmes critiques à fort enjeu (JO Paris 2024)."

### 3. Adapter les bullets
Lire `data/truth.json` pour les bullet pools. Pour CHAQUE expérience :
- Sélectionner les bullets les plus pertinents du pool correspondant au track
- **Réécrire** chaque bullet pour intégrer naturellement les keywords de l'offre quand c'est honnête
- Le bullet doit répondre implicitement à un besoin de l'offre, pas juste lister une techno

Règles par expérience :
- **Freelance (4 bullets)** : expérience la plus modifiable — adapter fortement. Choisir les bullets qui parlent des technos et du contexte de l'offre. Si l'offre est Java/backend, prendre les bullets microservices Spring Boot. Si IA, prendre les bullets RAG/LLM.
- **Atos/JO (4 bullets)** : toujours mettre en avant la criticité et l'échelle des JO. Tech → termes techniques (Spring Boot, OpenShift, GraphQL). Consulting → pilotage, architecture, DevSecOps.
- **Adria (3 bullets)** : si l'offre est bancaire/finance → toujours inclure le bullet BNDE. Sinon, prendre les bullets les plus proches techno.
- **SQLI (2 bullets)** : garder les plus pertinents par rapport à la stack.

Adapter le ton selon l'entreprise :
- **startup** : verbes d'ownership et d'impact ("Livré", "Conçu de bout en bout", "Autonome sur")
- **esn** : polyvalence et diversité ("Intervenu sur", "Contribué à plusieurs projets")
- **grand_groupe** : rigueur et process ("Mis en place", "Garanti", "Assuré la conformité")
- **cabinet_conseil** : cadrage et pilotage ("Cadré", "Piloté", "Défini la trajectoire")

### 4. Générer la lettre de motivation

**Structure obligatoire (5 paragraphes) :**

1. **Accroche formation + intention** : "Diplômé d'un Master 2 MIAGE [...] Dauphine-PSL et d'un diplôme d'ingénieur [...] ENSIAS, je souhaite candidater pour le poste de [poste] au sein de [entreprise]."

2. **Expérience Atos/JO** : Parler de l'alternance chez ATOS dans le cadre des JO Paris 2024. Mentionner 2-3 réalisations **concrètes et spécifiques à ce que demande l'offre**. Mentionner que la mission devait déboucher sur une embauche mais les difficultés financières d'Atos ont conduit à son dépôt de bilan.

3. **Polyvalence + freelance** : Parler de la polyvalence et des secteurs variés (bancaire chez Adria, sport chez Atos). Puis parler de l'expérience freelance en mettant en avant les compétences **directement pertinentes pour cette offre précise**.

4. **Lien avec l'offre** : Ce paragraphe doit montrer qu'Omar a lu et compris l'offre. Citer des éléments **spécifiques** : le nom de l'équipe, le contexte (R&D, migration, scale-up...), la stack exacte mentionnée dans l'offre. Expliquer pourquoi ce poste spécifiquement et pas un autre.

5. **Motivation entreprise + closing** : Une phrase spécifique sur l'entreprise (sa mission, un produit, une valeur concrète — PAS juste "vos valeurs"). Terminer par : "Je serais ravi de vous rencontrer pour échanger sur ma candidature et vous présenter plus en détail mon parcours et ma motivation à rejoindre vos équipes."

**Règles lettre :**
- **NE PAS inclure** "Madame, Monsieur," ni formule de politesse finale dans le body
- Le body commence directement par le paragraphe 1
- Ton soutenu mais pas guindé, pas de "je me permets de"
- En français, séparer les paragraphes par `\n\n`
- Doser l'assurance selon l'expérience réelle : si expérience partielle dans un domaine → "j'ai eu l'occasion de" ou "j'ai contribué à", pas "je maîtrise"

### 5. Checklist qualité avant de compiler

Vérifier chaque point avant d'écrire le JSON :

**CV :**
- [ ] `title_suggestion` : n'est PAS le titre exact de l'offre, mais un équivalent naturel
- [ ] `adapted_summary` : contient au moins 1 techno ou domaine nommé dans l'offre
- [ ] `adapted_summary` : ne contient pas "X ans d'expérience"
- [ ] Bullet `freelance[0]` : mentionne une techno de l'offre
- [ ] Aucun bullet ne contient de tiret `-` dans une phrase (sauf sigles : CI/CD, Spring Boot...)

**Lettre :**
- [ ] §2 (Atos) : mentionne 2 réalisations concrètes qui matchent l'offre, pas juste des technos
- [ ] §4 (lien) : contient un détail spécifique de l'offre (nom d'équipe, contexte, stack précise)
- [ ] §5 (motivation) : mentionne quelque chose de spécifique à l'entreprise (pas "vos valeurs" en général)
- [ ] Ton dosé : pas de sur-assurance sur des domaines partiellement maîtrisés

### 6. Écrire le fichier JSON
Écrire le résultat dans `data/latest_inspo.json` avec cette structure exacte :
```json
{
  "analysis": {
    "track": "tech|consulting",
    "keywords": ["..."],
    "seniority": "junior|mid|senior",
    "tone": "startup|esn|grand_groupe|cabinet_conseil",
    "title_suggestion": "titre adapté, PAS le titre exact de l'offre",
    "adapted_summary": "2-3 phrases réécrites pour cette offre précise",
    "company_name": "nom nettoyé (sans ex-...)",
    "offer_location": "ville de l'offre",
    "company_address": "adresse complète si connue, sinon vide"
  },
  "adapted_bullets": {
    "experiences": [
      {"id": "freelance", "bullets": ["...(4 bullets)..."]},
      {"id": "atos",      "bullets": ["...(4 bullets)..."]},
      {"id": "adria",     "bullets": ["...(3 bullets)..."]},
      {"id": "sqli",      "bullets": ["...(2 bullets)..."]}
    ]
  },
  "letter": {
    "company_name": "Nom de l'entreprise",
    "company_address": "Adresse ou vide",
    "position": "Titre du poste",
    "body": "5 paragraphes séparés par \\n\\n, sans Madame/Monsieur ni formule de politesse"
  }
}
```

### 7. Compiler les PDFs
```bash
cd /Users/nailferroukhi/Documents/mass
./gen
```
Le script `./gen` gère le PATH pdflatex, l'activation du venv, la compilation, et ouvre le dossier automatiquement.

### 8. Fiche de préparation (dans le chat)
Après compilation, fournir :
- **Résumé du poste** : ce qu'on attend du candidat en 3 points
- **Points forts** : ce qui matche le mieux dans le profil Omar
- **À préparer** : 3-4 questions techniques probables + sujets à réviser
- **Questions à poser** : 3 questions pertinentes qui montrent qu'on a lu l'offre
- **Point de vigilance** : si l'offre demande quelque chose qu'Omar maîtrise partiellement

---

## Stratégies par plateforme

La stratégie de génération varie selon la source de l'offre. Identifier la source avant de générer.

### WTTJ (Welcome to the Jungle)
- Contexte : startups, scale-ups, entreprises tech affichant leur culture
- Tone : **startup** — ownership, impact direct, livraison end-to-end
- Freelance : présenter comme freelance tech autonome, delivery de bout en bout
- Lettre §5 : citer un élément concret visible sur leur page WTTJ (produit, mission, valeur spécifique)
- Registre : direct, sans langue de bois

### LinkedIn
- Contexte : mix ESN, grands groupes, scale-ups
- Détecter depuis le nom de l'entreprise + description :
  - ESN/SSII → tone **esn**, polyvalence multi-clients
  - Grand groupe → tone **grand_groupe**, process et rigueur
  - Startup/scale-up → tone **startup**, impact et ownership
- Lettre §5 : chercher un élément distinctif de l'entreprise publiquement visible

### France Travail
- Contexte : PME, ESN, quelques grands groupes
- Tone par défaut : **esn**
- Si CDI : mentionner explicitement la volonté de s'inscrire dans la durée
- Registre : professionnel classique

### Choisir le Service Public (CSP — fonction publique)
- Contexte : ministères, universités, organismes publics, collectivités
- Tone : **grand_groupe** avec nuance service public

**Règle spéciale — expérience Freelance :**
Ne PAS présenter comme "Freelance". Renommer en :
- "Projet entrepreneurial et développement logiciel" ou
- "Développement indépendant — Mission IA/Backend" (adapter selon l'offre)
Garder les mêmes bullets mais avec registre sobre, non startup.

**Règle spéciale — Atos/JO :**
Ne PAS mentionner "dépôt de bilan". Remplacer par : "la mission s'est achevée à l'issue des Jeux Olympiques de Paris 2024."

**Bullets :**
- Atos : criticité, gestion de charge, équipe structurée → très valorisé dans le public
- Adria : contexte institutionnel (BNDE = banque nationale), rigueur processus

**Lettre :**
- §4 : montrer la compréhension du contexte service public, de l'enjeu d'intérêt général
- §5 : mentionner la mission de l'organisme ("contribuer à la modernisation des SI de l'État", "soutenir la transformation numérique de l'enseignement supérieur", etc.)
- Registre : formel, orienté mission collective plutôt qu'impact individuel

---

## Règles ABSOLUES
- Le profil est celui d'**Omar Ajraoui**, ingénieur logiciel
- Deux tracks : TECH (dev, devops, fullstack) et CONSULTING (stratégie SI, transformation)
- L'expérience freelance (Nov 2024 à Jan 2026) est la plus flexible — c'est là qu'on adapte le plus
- Les JO/Atos c'est le gros selling point — toujours mettre en avant
- **NE JAMAIS INVENTER** de technologie ou expérience absente de truth.json
- **NE JAMAIS écrire "X ans d'expérience"** (ni 3 ans, ni 2 ans, jamais)
- **JAMAIS de tirets (-)** dans les phrases. Réservés aux sigles (CI/CD, Spring Boot, Dauphine-PSL). Dans les phrases : virgules, points ou reformuler.
- LinkedIn : `linkedin.com/in/omarajraoui`
- **Adresse adaptée par ville** via `offer_location` dans l'analysis :
  - Paris / IDF → 27 Rue du Javelot, 75013 Paris
  - Lyon → 69 Rue Eugène Pons, 69004 Lyon
  - Lille → Villeneuve d'Ascq, 59491
  - Marseille / Sud → La Cannebière, 13001 Marseille
  - Autres villes → Paris par défaut

## Scraping
- **WTTJ** : API Algolia (index `wttj_jobs_production_fr`, app ID `CSEKHVMS53`)
- **France Travail** : HTML scraping
- Filtrer : France, 0-3 ans XP, CDI/CDD, < 7 jours
- Trier par fraîcheur puis XP requis (0 XP en premier)
