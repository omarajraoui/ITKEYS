"""
Moteur de génération CV + Lettre.
Mode principal : appel Claude CLI (même auth que Claude Code).
Fallback : rule-based si CLI indisponible.
"""

import json
import os
import re
import subprocess
import shutil
import requests as _requests
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Ensure pdflatex is in PATH
os.environ["PATH"] = "/usr/local/texlive/2026basic/bin/universal-darwin:" + os.environ.get("PATH", "")

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
TRUTH_PATH = os.path.join(DEFAULT_DATA_DIR, "truth.json")
CLAUDE_MD_PATH = os.path.join(os.path.dirname(__file__), "..", "CLAUDE.md")


def load_truth(data_dir=None):
    path = os.path.join(data_dir, "truth.json") if data_dir else TRUTH_PATH
    with open(path, "r") as f:
        return json.load(f)


# ─── Prompt Claude ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un expert en rédaction de candidatures techniques pour le candidat décrit dans le profil.
Tu reçois une offre d'emploi et un profil candidat (truth.json).

INSTRUCTION CRITIQUE : Tu dois répondre avec UN SEUL bloc JSON valide. RIEN d'autre.
Pas de texte avant, pas de texte après, pas d'explication, pas de markdown, pas de ```json```.
Ne tente PAS d'écrire dans un fichier. Ne demande PAS de permission. Retourne juste le JSON brut sur stdout.

════════════════════════════════════════
RÈGLE CRITIQUE — PERSONNE GRAMMATICALE
════════════════════════════════════════
La lettre de motivation est écrite À LA PREMIÈRE PERSONNE (je, j'ai, mon, ma, mes).
JAMAIS à la 3ème personne. JAMAIS "Omar a...", "Le candidat a...", "Il a...".
Toujours : "j'ai conçu", "mon alternance", "j'ai participé", "je serais ravi".
Le summary du CV utilise aussi la 1ère personne implicite (pas de "je" mais pas de "il" non plus).

RÈGLE FONDAMENTALE : tu ne modifies jamais les faits. Tu modifies uniquement la manière de présenter l'expérience pour la rendre pertinente vis-à-vis de l'offre.

Contexte candidat :
- 1 an d'alternance chez ATOS (JO Paris 2024)
- 1 expérience freelance (mission client + initiative entrepreneuriale)
- Objectif : obtenir un CDI rapidement
- Stratégie : se positionner sur un large éventail de postes (backend, devops, IA, fullstack, consulting)

════════════════════════════════════════
RÈGLES ABSOLUES
════════════════════════════════════════
- JAMAIS de tirets (-) dans les phrases. Virgules, points ou reformuler.
- La lettre DOIT tenir sur UNE SEULE PAGE. Paragraphes concis (3-4 phrases max chacun).
- Ne JAMAIS inventer de technologie, chiffre ou expérience absente du truth.json.
- Ne JAMAIS écrire "X ans d'expérience" nulle part (ni 2 ans, ni 3 ans, jamais).
- Nom d'entreprise nettoyé : enlever "(ex-...)", "(anciennement ...)", etc.
- title_suggestion : titre CV naturel, PAS le titre exact de l'offre.
- INTERDICTION d'écrire [Entreprise], [Poste] ou tout placeholder. Toujours le vrai nom.

════════════════════════════════════════
ÉTAPE 1 — ANALYSE DE L'OFFRE
════════════════════════════════════════
Extraire :
- Poste exact
- Stack (technologies demandées)
- Missions principales
- Contexte spécifique (produit, équipe, domaine, migration, R&D, scale...)
- Type entreprise : startup / esn / grand_groupe / cabinet_conseil

════════════════════════════════════════
ÉTAPE 2 — CHOIX DU TRACK (un seul)
════════════════════════════════════════
Choisir parmi : JAVA_BACKEND / DEVOPS_CLOUD / IA_GENAI / FULLSTACK / CONSULTING

Repositionnement selon le track :
  JAVA_BACKEND  → Spring Boot, APIs, microservices, migration
  DEVOPS_CLOUD  → CI/CD, Docker, OpenShift, déploiement, automatisation, Terraform, Ansible
  IA_GENAI      → RAG, LLM, PageIndex, expérimentation, chatbot
  FULLSTACK     → backend Spring Boot + React frontend, intégration complète
  CONSULTING    → compréhension besoin, structuration, coordination, livraison, cadrage

════════════════════════════════════════
ÉTAPE 3 — SÉLECTION MISSION FREELANCE (une seule, cohérente avec le track)
════════════════════════════════════════
Les projets freelance réels d'Omar :
  A. Mission client via réseau (principale) : migration e-commerce monolithe → microservices Java Spring Boot + frontend React + CI/CD GitLab Docker.
     Inclut aussi un chatbot IA interne : indexation PageIndex + LLM + interrogation langage naturel (même client, même mission).
  B. Kodelume (initiative entrepreneuriale) : pipeline agentique de prospection LLM + agents IA pour qualification B2B.
  C. Exploration RAG personnelle : architecture RAG Python, LLM — projet perso de veille, PAS livré pour un client.

Sélection OBLIGATOIRE :
  JAVA_BACKEND  → projet A (microservices, migration, Docker, CI/CD). 4 bullets sur ce projet.
  DEVOPS_CLOUD  → projet A (CI/CD GitLab Docker, containerisation, pipeline automatisé).
  IA_GENAI      → projet A volet chatbot (PageIndex, LLM, indexation) + Kodelume si pertinent.
  FULLSTACK     → projet A (React front + Java back, end-to-end).
  CONSULTING    → projet A cadré comme refonte architecturale (cadrage, trajectoire, pilotage).

INTERDIT : mélanger les projets dans les 4 bullets. Pas de Terraform/Ansible/Azure/GCP dans les bullets freelance (c'est Atos).

════════════════════════════════════════
ÉTAPE 4 — GÉNÉRATION DE BRIDGES (OBLIGATOIRE AVANT D'ÉCRIRE)
════════════════════════════════════════
Créer 3 à 5 correspondances concrètes :
  besoin de l'offre → expérience réelle d'Omar

Exemple :
  "Migration monolithe → microservices" → mission freelance : migration e-commerce Java Spring Boot
  "CI/CD GitLab" → Atos : pipelines GitLab CI/CD + DevSecOps SonarQube/Trivy
  "Architecture microservices" → Adria BNDE : microservices bancaires Spring Boot

RÈGLE : aucune phrase de la lettre ou du CV ne doit être écrite sans lien réel avec une expérience.
Les bridges sont inclus dans le JSON de sortie pour traçabilité.

════════════════════════════════════════
ÉTAPE 5 — BULLETS CV
════════════════════════════════════════
Réécrire chaque bullet en utilisant les bridges. Intégrer naturellement 1-2 mots-clés de l'offre quand c'est honnête.

Adapter le ton selon l'entreprise :
  startup      → ownership : "Livré", "Conçu de bout en bout", "Déployé seul"
  esn          → polyvalence : "Intervenu sur", "Contribué à plusieurs projets"
  grand_groupe → rigueur : "Mis en place", "Assuré la conformité", "Garanti"
  conseil      → cadrage : "Cadré", "Piloté", "Défini la trajectoire"

DOSAGE DE L'ASSURANCE (CRITIQUE) :
Omar a contribué à des projets microservices, il n'est pas architecte microservices.
- Utiliser "j'ai contribué à", "j'ai participé à", "j'ai pris en charge l'implémentation de"
- JAMAIS "j'ai conduit", "j'ai architecturé", "je maîtrise" pour les microservices
- Pour les API REST, tests, CI/CD, Docker : Omar les a vraiment faits → verbes directs OK
- Pour l'architecture, les choix techniques : "j'ai participé à la conception", pas "j'ai conçu"

Si l'offre demande une techno absente du profil → parler du concept le plus proche.
Exemple : Kafka demandé mais absent → parler d'architecture asynchrone ou de messaging.

ATOS (4 bullets) selon le track :
  JAVA_BACKEND/FULLSTACK → CAM/VAM apps + GraphQL + Spring Boot + DevSecOps
  DEVOPS_CLOUD           → OpenShift HA + Terraform/Ansible + Prometheus/Grafana + CI/CD
  IA_GENAI               → systèmes critiques haute dispo + monitoring + architecture scalable
  CONSULTING             → architecture SI, continuité de service, DevSecOps, pilotage

ADRIA (3 bullets) : BNDE banking obligatoire si JAVA_BACKEND. Plugin JIRA si FULLSTACK/CONSULTING. CI/CD Docker si DEVOPS.
SQLI (2 bullets) : les 2 les plus proches de la stack demandée.

════════════════════════════════════════
ÉTAPE 6 — LETTRE (5 paragraphes, séparés par \\n\\n)
════════════════════════════════════════
En français. Sans "Madame, Monsieur," ni formule de politesse finale.

CONTRAINTE ABSOLUE : la lettre doit tenir sur UNE SEULE PAGE A4.
Cela signifie : paragraphes concis (3-4 phrases max chacun), pas de phrases à rallonge.
Au total : 250-350 mots maximum pour le body entier. Privilégier la densité à la longueur.

§1 — ACCROCHE (2 phrases max, PAS de formule template)
INTERDIT : "je souhaite candidater pour le poste de X au sein de Y" — trop générique.
À la place : résumer la trajectoire en 2 phrases qui créent un lien naturel avec le poste.
Modèle : "Diplômé d'un Master 2 MIAGE de l'Université Paris Dauphine-PSL et d'un diplôme d'ingénieur de l'ENSIAS, j'ai construit mon parcours autour de [domaine clé du poste], des applications critiques des JO Paris 2024 jusqu'à [expérience récente pertinente]. Le poste que propose [ENTREPRISE] s'inscrit directement dans cette trajectoire."

§2 — ATOS / JO PARIS 2024 (3 phrases max)
Commencer par : "Mon alternance chez ATOS dans le cadre des Jeux Olympiques de Paris 2024 s'est achevée en octobre 2024 à l'issue de l'événement."
Puis : 2 réalisations CONCRÈTES utilisant les bridges. Verbe d'action + contexte + résultat.
PAS de liste de technos. Des phrases qui montrent ce qui a été fait et pourquoi c'était exigeant.

§3 — FREELANCE (récent) + ADRIA (une seule histoire, ordre chronologique inversé)
IMPORTANT : la mission freelance est l'expérience LA PLUS RÉCENTE d'Omar (Nov 2024 - Jan 2026). Elle doit être mentionnée EN PREMIER dans ce paragraphe.
1. 2-3 phrases sur UN SEUL projet freelance selon le track :
   Framing obligatoire : "Plus récemment, une mission obtenue via mon réseau m'a permis de [ce qui a été construit]."
   JAVA_BACKEND  : "...participer à la migration d'une application e-commerce d'une architecture monolithique vers des services Spring Boot, en prenant en charge la collecte des besoins client, l'implémentation des API REST, les tests d'intégration et le déploiement via le pipeline CI/CD GitLab."
   DEVOPS_CLOUD  : "...mettre en place le pipeline CI/CD GitLab et la conteneurisation Docker d'un projet e-commerce en cours de migration vers une architecture distribuée."
   IA_GENAI      : "...concevoir et livrer un chatbot IA pour usage interne, intégrant PageIndex pour l'indexation documentaire et permettant des interrogations en langage naturel, déployé en production via Docker."
   FULLSTACK     : "...participer à la migration d'une application e-commerce vers des services Spring Boot avec un frontend React, en prenant en charge l'implémentation des API, l'interface utilisateur et le pipeline de livraison."
   CONSULTING    : "...cadrer la refonte architecturale d'une plateforme e-commerce, en contribuant à la définition de la cible technique et en assurant la coordination entre les besoins fonctionnels et les contraintes de développement."
2. 1 phrase sur Adria, contexte le plus proche de l'offre :
   - Bancaire : "Auparavant, chez ADRIA Business Technology, j'avais développé des microservices Spring Boot pour un client bancaire (BNDE)..."
   - Plugin JIRA : "Auparavant, chez ADRIA, j'avais conçu un plugin JIRA React et Java Spring Boot de bout en bout..."
   - DevOps : "Auparavant, chez ADRIA, j'avais mis en place les pipelines CI/CD GitLab avec déploiement Docker..."

§4 — LIEN SPÉCIFIQUE AVEC L'OFFRE (le paragraphe CRITIQUE, 3-4 phrases)
Utiliser au moins 2 bridges. Citer un élément SPÉCIFIQUE de l'offre (nom du système, de l'équipe, contexte exact).
Exemples de ce qu'on veut :
  ✓ "L'équipe Platform Core que vous décrivez, chargée de migrer les services legacy vers une architecture microservices..."
  ✓ "Le contexte de refonte de votre pipeline de données temps réel avec Kafka et Spark..."
Si l'offre est vague : citer la stack exacte demandée et expliquer pourquoi cette combinaison précisément.

§5 — MOTIVATION ENTREPRISE + CLOSING (2 phrases)
1 phrase avec un fait CONCRET sur l'entreprise (mission, produit, initiative récente).
Terminer par : "Je serais ravi de vous rencontrer pour échanger sur ma candidature et vous présenter plus en détail mon parcours et ma motivation à rejoindre vos équipes."

════════════════════════════════════════
RÈGLES ANTI-GÉNÉRIQUE (STRICTES)
════════════════════════════════════════
INTERDIT dans la lettre :
  ✗ "vos valeurs"
  ✗ "votre entreprise" (utiliser le vrai nom)
  ✗ "votre culture d'innovation"
  ✗ "je suis passionné"
  ✗ "je souhaite mettre à profit"
  ✗ "votre offre correspond à mes compétences"
  ✗ "ce poste m'intéresse car il correspond à mon profil"
  ✗ "mon expérience me permettrait de contribuer rapidement"
  ✗ toute paraphrase vague de l'offre

OBLIGATOIRE : éléments concrets, liens explicites, ton sobre et crédible.

════════════════════════════════════════
RÈGLES CSP (service public uniquement)
════════════════════════════════════════
- Renommer "Freelance" → "Projet entrepreneurial et développement logiciel".
- §2 : "la mission s'est achevée à l'issue des Jeux Olympiques de Paris 2024."
- §3 : registre sobre, pas de "startup", pas de verbes d'ownership fort.
- §4 : montrer la compréhension du contexte service public et de l'enjeu d'intérêt général.
- §5 : mentionner la mission de l'organisme (modernisation SI, transformation numérique...).
- Registre : formel, orienté mission collective plutôt qu'impact individuel."""


def _fetch_company_context(company_name, offer_description=""):
    """Cherche une courte description de l'entreprise via DuckDuckGo.
    Fallback : extrait le premier paragraphe de la description de l'offre.
    Results are cached to avoid re-fetching."""
    if not company_name or len(company_name) < 3:
        return ""

    cache_key = company_name.lower().strip()
    if cache_key in _company_ctx_cache:
        return _company_ctx_cache[cache_key]

    result = ""
    try:
        r = _requests.get(
            "https://api.duckduckgo.com/",
            params={"q": company_name, "format": "json", "no_html": "1", "skip_disambig": "1"},
            timeout=4,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            data = r.json()
            abstract = (data.get("AbstractText") or "").strip()
            if len(abstract) > 50:
                result = abstract[:400]
    except Exception:
        pass

    if not result and offer_description:
        lines = [l.strip() for l in offer_description.split("\n") if l.strip()]
        for line in lines[:5]:
            if len(line) > 60 and company_name.lower()[:6] in line.lower():
                result = line[:300]
                break
        if not result and lines:
            result = lines[0][:300]

    _company_ctx_cache[cache_key] = result
    return result


PLATFORM_STRATEGIES = {
    "wttj": """
PLATEFORME : Welcome to the Jungle (startups / scale-ups)
- Tone par défaut : startup (ownership, impact, vitesse de livraison)
- Bullets freelance : mettre en avant l'autonomie totale, le delivery end-to-end
- Lettre §5 : citer quelque chose de spécifique à l'entreprise (produit, culture, missions visibles sur WTTJ)
- Registre : direct, concret, pas de langue de bois
""",
    "linkedin": """
PLATEFORME : LinkedIn (mix ESN / grands groupes / scale-ups)
- Détecter le type d'entreprise depuis son nom et la description, adapter le tone en conséquence
- Si ESN/SSII : mettre en avant la polyvalence multi-clients, l'adaptabilité rapide
- Si grand groupe : process, rigueur, capacité à travailler dans un contexte structuré
- Si startup : ownership et impact direct
- Lettre §5 : chercher un élément distinctif de l'entreprise visible publiquement
""",
    "francetravail": """
PLATEFORME : France Travail (PME / ESN / quelques grands groupes)
- Tone par défaut : esn (polyvalence, diversité des missions)
- Insister sur la stabilité CDI si l'offre est CDI
- Lettre §4 : mentionner explicitement la nature du contrat et la volonté de s'inscrire dans la durée
- Registre : professionnel classique, pas trop startup
""",
    "csp": """
PLATEFORME : Choisir le Service Public (fonction publique — ministères, universités, organismes publics)
- Tone : grand_groupe avec une nuance service public (mission d'intérêt général, rigueur, durabilité)
- IMPORTANT — Expérience freelance : NE PAS la présenter comme "Freelance".
  La renommer "Projet entrepreneurial et développement logiciel" ou "Développement indépendant — Mission IA/Backend".
  Garder les mêmes bullets mais avec un registre plus sobre, moins "startup".
- Bullets Atos/JO : insister sur la criticité, la gestion de charge, le travail en équipe structurée — très valorisé dans le public
- Bullets Adria : mettre en avant le contexte institutionnel (BNDE = banque nationale), la rigueur processus
- Lettre §4 : montrer la compréhension du contexte service public, du périmètre de la mission, de l'enjeu d'intérêt général
- Lettre §5 : mentionner la mission de l'organisme (ex: "contribuer à la modernisation des SI de l'État", "soutenir la transformation numérique de l'enseignement supérieur")
- NE PAS mentionner "dépôt de bilan" d'Atos dans ce contexte — remplacer par "la mission s'est achevée à l'issue des Jeux"
- Registre : formel, structuré, orienté mission collective plutôt qu'impact individuel
""",
}


def _slim_truth(truth, likely_track=None):
    """Strip compiler-only fields from truth.json to reduce prompt size.
    If likely_track is set, only include that track's bullets to save ~40% tokens."""
    # Strip profile to essentials for the prompt
    profile = {k: truth["profile"][k] for k in ["name", "languages"] if k in truth["profile"]}
    slim = {
        "profile": profile,
        "experiences": [],
        "skills": truth.get("skills", {}),
    }

    # Determine which bullet tracks to include
    tracks_to_include = None
    if likely_track and likely_track in ("tech", "consulting"):
        tracks_to_include = [likely_track]
    else:
        tracks_to_include = ["tech", "consulting"]

    for exp in truth["experiences"]:
        pool = exp.get("bullets_pool", {})
        slim_pool = {t: pool[t] for t in tracks_to_include if t in pool}
        slim["experiences"].append({
            "id": exp["id"],
            "company": exp["company"],
            "stack": exp.get("stack", [])[:8],  # Cap stack at 8 items
            "bullets_pool": slim_pool,
        })
    return slim


def _slim_offer(offer):
    """Strip large fields from offer and trim description to key content."""
    keep = ["title", "company", "location", "source", "url", "contract", "salary"]
    slim = {k: offer[k] for k in keep if k in offer}

    # Trim description: keep first 2000 chars (the rest is usually legal/benefits boilerplate)
    desc = offer.get("description", "")
    if len(desc) > 2000:
        # Try to cut at a paragraph boundary
        cut = desc[:2000].rfind("\n\n")
        if cut > 1000:
            desc = desc[:cut]
        else:
            desc = desc[:2000] + "…"
    slim["description"] = desc
    return slim


# Company context cache (avoid re-fetching same company)
_company_ctx_cache = {}


def _guess_track(offer):
    """Pre-detect likely track from offer to optimize prompt size."""
    text = f"{offer.get('title', '')} {offer.get('description', '')[:500]}".lower()
    consulting_signals = sum(1 for k in ["consultant", "conseil", "si", "transformation", "pilotage", "moa", "amoa"] if k in text)
    if consulting_signals >= 2:
        return "consulting"
    return "tech"


GENERIC_SYSTEM_PROMPT = """Tu es un expert en redaction de candidatures. Tu recois une offre d'emploi et un profil candidat (truth.json).

INSTRUCTION CRITIQUE : Tu dois repondre avec UN SEUL bloc JSON valide. RIEN d'autre.

La lettre de motivation est ecrite A LA PREMIERE PERSONNE (je, j'ai, mon, ma, mes).
JAMAIS a la 3eme personne.

REGLE FONDAMENTALE : tu ne modifies jamais les faits. Tu adaptes la presentation de l'experience pour la rendre pertinente vis-a-vis de l'offre.

REGLES :
- Ne JAMAIS inventer de technologie, chiffre ou experience absente du truth.json.
- Ne JAMAIS ecrire "X ans d'experience" nulle part.
- title_suggestion : titre CV naturel adapte, PAS le titre exact de l'offre.
- Nom d'entreprise nettoye (sans "ex-..." ou "anciennement...").
- INTERDICTION d'ecrire [Entreprise], [Poste] ou tout placeholder.
- La lettre DOIT ABSOLUMENT tenir sur UNE SEULE PAGE. Maximum 4 paragraphes COURTS (3-4 phrases chacun). Si trop long, COUPE.

ETAPES :
1. Analyser l'offre (track, keywords, tone, seniority)
2. Adapter le summary (2-3 phrases, mentionner 1-2 technos de l'offre)
3. Pour CHAQUE experience du truth.json, selectionner et adapter les bullets les plus pertinents
4. Ecrire une lettre de motivation en 4-5 paragraphes:
   - Accroche formation + intention
   - Experience principale adaptee a l'offre
   - Polyvalence et autres experiences
   - Lien specifique avec l'offre (citer des elements precis)
   - Motivation entreprise + closing

FORMAT DE SORTIE (JSON uniquement):
{
  "analysis": {
    "track": "tech|consulting",
    "keywords": ["..."],
    "seniority": "junior|mid|senior",
    "tone": "startup|esn|grand_groupe|cabinet_conseil",
    "title_suggestion": "titre adapte",
    "adapted_summary": "2-3 phrases",
    "company_name": "nom nettoye",
    "offer_location": "ville",
    "company_address": ""
  },
  "adapted_bullets": {
    "experiences": [
      {"id": "exp_id", "bullets": ["bullet1", "bullet2", "..."]}
    ]
  },
  "letter": {
    "company_name": "Nom",
    "company_address": "",
    "position": "Titre du poste",
    "body": "paragraphes separes par \\n\\n"
  }
}
"""


def _is_omar_profile(truth):
    """Check if this is Omar's admin profile."""
    name = truth.get("profile", {}).get("name", "").lower()
    return "omar" in name and "ajraoui" in name


def _build_prompt(offer, truth, user_prompt=None):
    """Construit le prompt complet pour Claude."""
    source = offer.get("source", "")
    platform_block = PLATFORM_STRATEGIES.get(source, "")

    company_ctx = _fetch_company_context(
        offer.get("company", ""),
        offer.get("description", ""),
    )

    likely_track = _guess_track(offer)
    offer_text = json.dumps(_slim_offer(offer), ensure_ascii=False, indent=2)
    truth_text = json.dumps(_slim_truth(truth, likely_track=likely_track), ensure_ascii=False, indent=2)

    # Use Omar-specific prompt for admin, generic for everyone else
    system = SYSTEM_PROMPT if _is_omar_profile(truth) else GENERIC_SYSTEM_PROMPT

    platform_section = f"\n═══ STRATEGIE PLATEFORME ═══{platform_block}" if platform_block and _is_omar_profile(truth) else ""
    company_section  = f"\n═══ CONTEXTE ENTREPRISE ═══\n{company_ctx}\n" if company_ctx else ""

    user_instruction = ""
    if user_prompt:
        user_instruction = f"""
═══ INSTRUCTION UTILISATEUR — CECI EST L'INSTRUCTION LA PLUS IMPORTANTE ═══

L'UTILISATEUR DEMANDE: "{user_prompt}"

TU DOIS ABSOLUMENT APPLIQUER CETTE DEMANDE. Elle ANNULE et REMPLACE toute instruction precedente.
- Si on te dit "en anglais" → TOUT le contenu JSON (summary, bullets, lettre) DOIT etre en anglais.
- Si on te dit "raccourcis" → raccourcis.
- Si on te dit "change le titre en X" → change-le.
- GENERE LE JSON COMPLET avec la modification appliquee.
"""

    return f"""{system}
{company_section}
═══ OFFRE D'EMPLOI ═══
{offer_text}

═══ PROFIL CANDIDAT (truth.json) ═══
{truth_text}

═══ FORMAT DE SORTIE ATTENDU (JSON uniquement, rien d'autre) ═══
{{
  "analysis": {{
    "track": "tech|consulting",
    "keywords": ["..."],
    "seniority": "junior|mid",
    "tone": "startup|esn|grand_groupe|cabinet_conseil",
    "title_suggestion": "titre CV adapté, PAS le titre exact de l'offre",
    "adapted_summary": "2-3 phrases réécrites pour cette offre. Mentionner 1-2 technos clés. NE PAS dire X ans d'expérience.",
    "company_name": "nom nettoyé (sans ex-...)",
    "offer_location": "ville de l'offre",
    "company_address": ""
  }},
  "bridges": [
    "besoin offre → expérience Omar (3 à 5 correspondances concrètes)"
  ],
  "adapted_bullets": {{
    "experiences": [
      {{"id": "freelance", "bullets": ["...(4 bullets réécrits selon track)..."]}},
      {{"id": "atos", "bullets": ["...(4 bullets réécrits)..."]}},
      {{"id": "adria", "bullets": ["...(3 bullets)..."]}},
      {{"id": "sqli", "bullets": ["...(2 bullets)..."]}}
    ]
  }},
  "letter": {{
    "company_name": "...",
    "company_address": "",
    "position": "titre du poste",
    "body": "5 paragraphes séparés par \\n\\n, SANS Madame/Monsieur, SANS formule de politesse"
  }}
}}

RAPPEL : réponds UNIQUEMENT avec le JSON brut. Pas de texte, pas de markdown, pas de commentaire. Commence directement par {{ et termine par }}.
{user_instruction}"""


# ─── Appel Claude CLI ─────────────────────────────────────────────────────────

# Singleton API client (reused across calls)
_anthropic_client = None

def _get_client():
    global _anthropic_client
    if _anthropic_client is None:
        import os
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=api_key)
    return _anthropic_client

# Model IDs
_MODEL_MAP = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-4-5-20251001",
}


def _call_claude(prompt, model="sonnet"):
    """Appelle l'API Anthropic directement."""
    client = _get_client()
    if not client:
        print("ANTHROPIC_API_KEY not set")
        return None

    model_id = _MODEL_MAP.get(model, model)

    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": "{"},  # prefill to force JSON
            ],
        )

        text = response.content[0].text if response.content else ""
        # Prepend the { we prefilled
        text = "{" + text
        if text.strip():
            print(f"  API: {response.usage.input_tokens} in / {response.usage.output_tokens} out ({model_id.split('-')[1]})")
            return text.strip()
        print(f"Claude API returned empty response")
        return None
    except Exception as e:
        print(f"Claude API error: {e}")
        return None


def _extract_json(text):
    """Extrait le premier bloc JSON valide d'un texte."""
    # Chercher un bloc ```json ... ```
    match = re.search(r'```(?:json)?\s*\n(.*?)```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Chercher le premier { ... } complet
    depth = 0
    start = None
    for i, c in enumerate(text):
        if c == '{':
            if depth == 0:
                start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    start = None
    return None


_YEARS_EXP_RE = re.compile(r"\d+\s*ans?\s*d['\u2019]exp\u00e9rience", re.IGNORECASE)

_PLACEHOLDER_PATTERN = re.compile(
    r'\[(?:Entreprise|Nom de l\'entreprise|Société|Company|NomEntreprise|Nom Entreprise|'
    r'nom de l\'entreprise|entreprise|société|company)\]',
    re.IGNORECASE,
)


def _fix_placeholders(inspo):
    """Replace [Entreprise] and similar placeholders left by the LLM."""
    company = (
        inspo.get("analysis", {}).get("company_name")
        or inspo.get("letter", {}).get("company_name")
        or ""
    ).strip()
    if not company:
        return

    letter = inspo.get("letter", {})
    body = letter.get("body", "")
    if body and _PLACEHOLDER_PATTERN.search(body):
        letter["body"] = _PLACEHOLDER_PATTERN.sub(company, body)
        print(f"  [Fix] Placeholder [Entreprise] remplacé par '{company}'")

    # Also fix position placeholder
    _POS_PATTERN = re.compile(
        r'\[(?:Poste|Position|Titre|titre du poste|poste)\]',
        re.IGNORECASE,
    )
    position = letter.get("position", "")
    if position and _POS_PATTERN.search(body):
        letter["body"] = _POS_PATTERN.sub(position, letter["body"])


def _validate_and_fix(inspo, offer):
    """
    Validate and auto-repair LLM output. Returns (inspo, issues) where
    issues is a list of strings describing problems that could NOT be auto-fixed
    (requiring a retry).
    """
    issues = []
    fixed = []

    analysis  = inspo.get("analysis", {})
    bullets_e = inspo.get("adapted_bullets", {}).get("experiences", [])
    letter    = inspo.get("letter", {})
    body      = letter.get("body", "")

    # ── Auto-fix: placeholders ──────────────────────────────────────────────
    _fix_placeholders(inspo)
    body = letter.get("body", "")  # re-read after fix

    # ── Auto-fix: strip "X ans d'expérience" from bullets ──────────────────
    for exp in bullets_e:
        new_bullets = []
        for b in exp.get("bullets", []):
            cleaned = _YEARS_EXP_RE.sub("", b).strip().rstrip(',').strip()
            if cleaned != b:
                fixed.append(f"Bullet nettoyé ({exp['id']}): suppression 'X ans'")
            new_bullets.append(cleaned)
        exp["bullets"] = new_bullets

    # ── Auto-fix: strip leading "- " from bullets ───────────────────────────
    for exp in bullets_e:
        exp["bullets"] = [
            b[2:].strip() if b.startswith("- ") else b
            for b in exp.get("bullets", [])
        ]

    # ── Auto-fix: bullet count ───────────────────────────────────────────────
    id_map = {e["id"]: e for e in bullets_e}
    # For Omar's profile, check specific expected counts
    if all(eid in id_map for eid in ["freelance", "atos"]):
        EXPECTED = {"freelance": 4, "atos": 4, "adria": 3, "sqli": 2}
        for exp_id, expected_n in EXPECTED.items():
            exp = id_map.get(exp_id)
            if not exp:
                issues.append(f"Expérience '{exp_id}' manquante dans adapted_bullets")
                continue
            actual_n = len(exp.get("bullets", []))
            if actual_n != expected_n:
                issues.append(f"Bullets {exp_id}: {actual_n} au lieu de {expected_n}")
    # For other users, just check that each experience has at least 1 bullet
    else:
        for exp in bullets_e:
            if not exp.get("bullets"):
                issues.append(f"Expérience '{exp.get('id','')}' sans bullets")

    # ── Auto-fix: summary — remove "X ans" ──────────────────────────────────
    summary = analysis.get("adapted_summary", "")
    if _YEARS_EXP_RE.search(summary):
        cleaned = _YEARS_EXP_RE.sub("", summary).strip()
        analysis["adapted_summary"] = cleaned
        fixed.append("Summary: 'X ans d'expérience' supprimé")

    # ── Hard check: summary must mention at least one offer keyword ──────────
    offer_text = f"{offer.get('title','')} {offer.get('description','')}".lower()
    keywords   = analysis.get("keywords", [])
    summary_l  = analysis.get("adapted_summary", "").lower()
    if keywords and not any(k.lower() in summary_l for k in keywords[:10]):
        issues.append("Summary ne mentionne aucun keyword de l'offre")

    # ── Hard check: letter body paragraph count ─────────────────────────────
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
    is_omar_letter = all(eid in id_map for eid in ["freelance", "atos"])
    min_paragraphs = 5 if is_omar_letter else 3
    if len(paragraphs) < min_paragraphs:
        issues.append(f"Lettre: {len(paragraphs)} paragraphes au lieu de {min_paragraphs}")

    # ── Hard check: §4 must not be generic ──────────────────────────────────
    if len(paragraphs) >= 4:
        para4 = paragraphs[3].lower()
        GENERIC_P4 = [
            "votre offre correspond à mes compétences",
            "votre offre correspond parfaitement",
            "ce poste correspond",
            "ce poste m'intéresse",
            "mon profil correspond",
            "mes compétences correspondent",
        ]
        if any(g in para4 for g in GENERIC_P4):
            issues.append("§4 générique: ne cite aucun détail spécifique de l'offre")

    # ── Hard check: §5 must not use "vos valeurs" ───────────────────────────
    if len(paragraphs) >= 5:
        para5 = paragraphs[4].lower()
        if "vos valeurs" in para5 and "votre mission" not in para5 and "votre produit" not in para5:
            issues.append("§5: formule générique 'vos valeurs' sans contenu spécifique")

    # ── Hard check: tirets dans les bullets ─────────────────────────────────
    _DASH_IN_SENTENCE = re.compile(r'(?<![A-Z/])\s-\s(?![A-Z/])')
    dash_count = 0
    for exp in bullets_e:
        for b in exp.get("bullets", []):
            if _DASH_IN_SENTENCE.search(b):
                dash_count += 1
    if dash_count > 0:
        issues.append(f"{dash_count} bullet(s) contiennent un tiret dans une phrase")

    # ── Hard check: 3rd person in letter (must be 1st person) ────────────────
    candidate_name = inspo.get("analysis", {}).get("company_name", "")
    profile_name = ""
    # Try to get the candidate's first name from truth context
    for exp in bullets_e:
        pass  # just need the name from analysis
    # Check for 3rd person patterns using the candidate's actual name
    candidate_first = (inspo.get("analysis", {}).get("company_name", "") or "").split()[0] if False else ""
    # Get actual candidate name from the offer context or truth
    _THIRD_PERSON = re.compile(
        r'\b(?:le candidat|il a |elle a |son parcours|sa candidature|son expérience)\b',
        re.IGNORECASE,
    )
    third_person_matches = _THIRD_PERSON.findall(body)
    if third_person_matches:
        issues.append(f"Lettre: 3ème personne détectée ({', '.join(list(set(third_person_matches))[:3])}). Doit être à la 1ère personne (je/j'ai/mon)")

    # Also check summary for 3rd person
    summary_text = analysis.get("adapted_summary", "")
    third_in_summary = _THIRD_PERSON.findall(summary_text)
    if third_in_summary:
        issues.append(f"Summary: 3ème personne détectée ({', '.join(set(third_in_summary)[:2])})")

    # ── Closing letter check (Omar-specific, skip for English) ──────────
    body_lower = body.lower()
    has_fr_closing = "je serais ravi" in body_lower or "rencontrer" in body_lower
    has_en_closing = "look forward" in body_lower or "pleased to" in body_lower or "happy to discuss" in body_lower or "meet" in body_lower
    if not has_fr_closing and not has_en_closing and all(eid in id_map for eid in ["freelance", "atos"]):
        issues.append("Lettre: phrase de closing manquante")

    if fixed:
        print(f"  [Validate] Auto-fixes: {'; '.join(fixed)}")
    if issues:
        print(f"  [Validate] Problèmes: {'; '.join(issues)}")

    return inspo, issues


def generate_with_claude(offer, truth, user_prompt=None):
    """Génère via API Anthropic avec validation et retry. Retourne le dict inspo ou None."""
    prompt = _build_prompt(offer, truth, user_prompt=user_prompt)
    # Haiku for first gen (fast, cheap), Sonnet for user refinements (smarter)
    # Omar = always Sonnet (quality matters for his applications)
    # Other users = Haiku for first gen, Sonnet for modifications
    is_omar = _is_omar_profile(truth)
    model = "sonnet" if (user_prompt or is_omar) else "haiku"
    print(f"  Appel Claude API ({model}) pour {offer.get('company', '?')}...")

    for attempt in range(2):
        if attempt > 0:
            print(f"  Retry #{attempt} (problèmes détectés à la passe précédente)...")

        raw = _call_claude(prompt, model=model)
        if not raw:
            return None

        inspo = _extract_json(raw)
        if not inspo:
            print("  Erreur: impossible d'extraire le JSON de la réponse Claude")
            continue

        if "analysis" not in inspo or "adapted_bullets" not in inspo or "letter" not in inspo:
            print("  Erreur: JSON incomplet")
            continue

        inspo["analysis"]["apply_link"] = offer.get("url", "")

        # Normalize track for compiler (expects "tech" or "consulting")
        TRACK_MAP = {
            "JAVA_BACKEND": "tech", "DEVOPS_CLOUD": "tech", "IA_GENAI": "tech",
            "FULLSTACK": "tech", "CONSULTING": "consulting",
            "java_backend": "tech", "devops_cloud": "tech", "ia_genai": "tech",
            "fullstack": "tech", "consulting": "consulting",
        }
        raw_track = inspo["analysis"].get("track", "tech")
        inspo["analysis"]["track"] = TRACK_MAP.get(raw_track, raw_track)

        inspo, issues = _validate_and_fix(inspo, offer)

        # Blocker issues that require retry
        BLOCKERS = {"Lettre:", "Bullets ", "Expérience '", "Summary: 3"}
        blockers = [i for i in issues if any(i.startswith(b) for b in BLOCKERS)]

        if not blockers:
            print(f"  Claude OK: track={inspo['analysis']['track']}, title={inspo['analysis']['title_suggestion']}")
            return inspo

        if attempt == 0:
            print(f"  Retry pour: {'; '.join(blockers)}")
        else:
            # 2ème tentative — si problèmes structurels (JSON, bullets count) → échec dur
            structural = [i for i in issues if i.startswith("Expérience '") or i.startswith("Lettre:")]
            if structural:
                print(f"  Échec après retry — problèmes structurels: {'; '.join(structural)}")
                return None
            # Problèmes sémantiques seulement → retourner avec flag warning
            print(f"  [Warning] Retourné avec avertissements: {'; '.join(issues)}")
            inspo["_validation_warnings"] = issues
            return inspo

    return None


def _clean_company(name):
    name = re.sub(r"\s*\(ex[- ][^)]*\)", "", name)
    name = re.sub(r"\s*\(anciennement[^)]*\)", "", name, flags=re.IGNORECASE)
    return name.strip()


# ─── Fallback rule-based DÉSACTIVÉ ───────────────────────────────────────────
# Le fallback produisait des lettres inutilisables (keywords bruts dans les phrases,
# §4 générique, mélange incohérent de stacks). Supprimé volontairement.
# Si Claude échoue → erreur explicite dans le dashboard, rien ne compile.
# ─────────────────────────────────────────────────────────────────────────────


# ─── Orchestration ───────────────────────────────────────────────────────────

def generate_for_offer(offer, data_dir=None):
    """Pipeline complet : Claude CLI → validation → compile PDFs.
    data_dir: user-scoped data directory (data/users/{uid}). Falls back to data/.
    Lève une exception si Claude échoue ou produit un résultat non compilable.
    """
    from src.compiler import compile_cv, compile_letter
    from src.tracker import add_application

    base = data_dir or DEFAULT_DATA_DIR
    truth = load_truth(data_dir)

    inspo = generate_with_claude(offer, truth)
    if not inspo:
        raise RuntimeError(
            "Claude n'a pas pu générer une candidature valide pour cette offre. "
            "Vérifie que la clé ANTHROPIC_API_KEY est configurée dans .env et réessaie."
        )

    analysis = inspo["analysis"]
    adapted = inspo["adapted_bullets"]
    letter = inspo["letter"]

    # Sauvegarder latest_inspo.json
    inspo_path = os.path.join(base, "latest_inspo.json")
    with open(inspo_path, "w") as f:
        json.dump(inspo, f, ensure_ascii=False, indent=2)

    # Compiler
    def slugify(t):
        return t.lower().replace(" ", "_").replace("'", "").replace("/", "-")[:30]

    company_slug = slugify(analysis.get("company_name", "company"))
    title_slug = slugify(analysis["title_suggestion"])
    date_str = datetime.now().strftime("%Y%m%d")
    output_base = os.path.join(base, "output") if data_dir else "output"
    output_dir = os.path.join(output_base, f"{company_slug}_{title_slug}_{date_str}")

    # Use user-scoped templates dir if it exists, else default
    templates_dir = os.path.join(base, "templates") if data_dir and os.path.isdir(os.path.join(base, "templates")) else None
    cv_path = compile_cv(truth, analysis, adapted, output_dir, templates_dir=templates_dir)
    letter_path = compile_letter(letter, truth, output_dir, offer_analysis=analysis, templates_dir=templates_dir)

    # Summary
    summary = {**inspo, "cv_path": cv_path, "letter_path": letter_path}
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # Track
    db_path = os.path.join(base, "applications.db") if data_dir else None
    add_application(
        company=analysis.get("company_name", "Unknown"),
        role=analysis["title_suggestion"],
        track=analysis["track"],
        output_dir=output_dir,
        apply_link=analysis.get("apply_link", ""),
        db_path=db_path,
    )

    return {
        "output_dir": output_dir,
        "cv_path": cv_path,
        "letter_path": letter_path,
        "analysis": analysis,
        "inspo": inspo,
    }
