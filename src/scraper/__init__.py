"""
Scraper multi-source : WTTJ (Algolia API), France Travail (HTML + JSON-LD)
Scoring automatique des offres par rapport au profil Omar.
"""

import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlencode
import json
import time
import re
from datetime import datetime


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# WTTJ Algolia
ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_INDEX = "wttj_jobs_production_fr"

# Requêtes larges couvrant tout le profil Omar
SEARCH_QUERIES = [
    # Backend / Java
    "développeur java",
    "développeur spring boot",
    "développeur backend java",
    "ingénieur java",
    # Fullstack
    "développeur fullstack",
    "développeur full stack",
    "fullstack react java",
    "fullstack react spring",
    # Python / IA
    "développeur python",
    "ingénieur python django",
    "développeur IA",
    "ingénieur intelligence artificielle",
    "développeur GenAI",
    # DevOps / Cloud / Infra
    "ingénieur devops",
    "devops kubernetes",
    "ingénieur cloud",
    "SRE",
    "ingénieur infrastructure",
    # React / Front / Mobile React
    "développeur react",
    "développeur frontend react",
    "développeur front",
    "ingénieur front",
    "développeur react junior",
    "développeur react native",
    # Consulting / SI
    "consultant IT",
    "consultant transformation SI",
    "consultant systèmes information",
    "consultant technique IT",
    # Générique ingé logiciel
    "ingénieur logiciel",
    "ingénieur développement",
    "software engineer",
    "ingénieur études développement",
    # ESN / SSII bait (high volume, fast hiring)
    "ingénieur études et développement",
    "analyste développeur",
    "consultant technique junior",
    "développeur junior",
    "ingénieur développement junior",
    "développeur web junior",
    "ingénieur logiciel junior",
    "développeur java junior",
    "développeur fullstack junior",
    # CDD / missions courtes
    "développeur CDD",
    "ingénieur CDD informatique",
]

# Mots-clés du profil Omar pour le scoring
PROFILE_SKILLS = {
    # Score élevé (core skills)
    "java": 10, "spring boot": 10, "spring": 8, "react": 9, "react native": 7, "python": 9,
    "kubernetes": 8, "docker": 7, "devops": 8, "ci/cd": 7, "cicd": 7,
    "terraform": 7, "ansible": 7, "gitlab": 6, "fullstack": 9, "full stack": 9,
    "api rest": 7, "rest": 5, "microservices": 7, "graphql": 6,
    # Score moyen (connu)
    "django": 6, "postgresql": 5, "mysql": 5, "mongodb": 4,
    "openshift": 6, "prometheus": 5, "grafana": 5, "sonarqube": 4,
    "typescript": 6, "javascript": 5, "node": 4, "angular": 3,
    "azure": 5, "gcp": 5, "cloud": 5, "aws": 3,
    "agile": 4, "scrum": 4, "jira": 3,
    "linux": 4, "git": 3, "bash": 3,
    # IA / GenAI
    "ia": 6, "intelligence artificielle": 7, "llm": 7, "rag": 7,
    "genai": 7, "ia générative": 7, "machine learning": 4, "ml": 3,
    # Consulting
    "transformation": 5, "si": 4, "architecture": 5, "pilotage": 5,
}

# Mots-clés d'exclusion (offres non pertinentes)
# Exclusions sur le texte complet (titre + description)
EXCLUDE_KEYWORDS = [
    "alternance", "stage", "stagiaire", "apprenti", "apprentissage",
    "internship", "intern ", "intern-",
    "commercial", "marketing", "comptable", "rh", "ressources humaines",
    "développeur foncier", "photovoltaïque", "immobilier",
    "salesforce", "sap", "cobol", "mainframe",
    "manager", "directeur", "head of", "vp ",
    "handicap", "rqth", "travailleurs handicapés", "handicap-job",
    "talents handicap",
]

# Seniority — bloque dans le TITRE
_TITLE_SENIORITY = re.compile(
    r'\b(?:'
    r's[eé]nior|sr\b|'
    r'confirm[eé]|exp[eé]riment[eé]|'
    r'tech(?:nical)?\s*lead(?:er)?|'
    r'lead\s*d[eé]v(?:elop(?:p?eur?)?)?|'
    r'lead\s*(?:tech|engineer|ing[eé]nieur|backend|frontend|fullstack|developer|data|cloud|mobile|platform|software|sre)|'
    r'principal\s*(?:engineer|developer|d[eé]velop)|'
    r'staff\s*engineer|'
    r'expert\b|'
    r'architecte\b|'
    r'responsable\b|'
    r'business\s*developer'
    r')',
    re.IGNORECASE,
)

# Seniority — bloque aussi dans la DESCRIPTION (phrases claires de seniority)
_DESC_SENIORITY = re.compile(
    r'(?:'
    r'profil\s+senior|profil[s]?\s+confirm[eé]|'
    r'ing[eé]nieur\s+(?:cloud\s+)?senior|'
    r'd[eé]velop(?:peur|euse)?\s+senior|'
    r'consultant(?:e)?\s+senior|'
    r'nous\s+recherchons\s+un(?:e)?\s+.{0,20}senior|'
    r'expert(?:e)?\s+(?:en|dans|technique)|'
    r'architecte\s+(?:logiciel|technique|solution|cloud|si)|'
    r'lead\s+(?:dev|technique|developer|engineer)|'
    r'encadrer?\s+(?:une?\s+)?[eé]quipe|'
    r'manager?\s+(?:une?\s+)?[eé]quipe\s+de\s+\d|'
    r'pilotage?\s+strat[eé]gique|'
    r'exp[eé]riment[eé](?:e)?(?:\s|,|\.)|'
    r'exp[eé]rience\s+(?:significative|solide|avanc[eé]e|confirm[eé]e)'
    r')',
    re.IGNORECASE,
)

# Seniority penalty words — each occurrence penalizes the score (not hard block)
_SENIORITY_PENALTY_WORDS = [
    "confirmé", "confirmee", "confirmes", "expérimenté", "experimentee",
    "expérience significative", "experience significative",
    "expérience solide", "experience solide",
    "maîtrise avancée", "maitrise avancee",
    "autonomie totale", "référent technique", "referent technique",
    "encadrement", "management d'équipe", "management d equipe",
]

# Mots-clés qui boostent le score (correspond bien au profil)
BOOST_KEYWORDS = [
    "junior", "0-2 ans", "0-3 ans", "1-3 ans",
    "jeune diplômé", "première expérience", "débutant accepté",
    "débutant", "sortie d'école", "cdi", "cdd",
]

# Localisations prioritaires (score bonus)
PRIORITY_LOCATIONS = {
    # Tier 1 : villes prioritaires (+15)
    "paris": 15, "ile-de-france": 15, "île-de-france": 15,
    "lyon": 15, "lille": 15,
    "marseille": 15, "aix-en-provence": 15, "antibes": 15,
    "sophia-antipolis": 15, "sophia antipolis": 15, "nice": 15,
    "cannes": 15, "toulon": 12, "montpellier": 12,
    # Banlieue parisienne
    "la défense": 15, "la defense": 15, "boulogne-billancourt": 15,
    "issy-les-moulineaux": 15, "nanterre": 15, "saint-denis": 15,
    "levallois-perret": 15, "rueil-malmaison": 15,
    "courbevoie": 15, "puteaux": 15, "clichy": 15,
    "montreuil": 15, "fontenay-sous-bois": 15,
    "bois-colombes": 15, "massy": 15, "villejuif": 15,
    "ivry-sur-seine": 15, "le plessis-robinson": 15,
    "saint-ouen": 15, "guyancourt": 15, "vélizy": 15,
    # Dept 06/13 (Côte d'Azur / Bouches-du-Rhône)
    "grasse": 15, "mougins": 15, "valbonne": 15,
    # Tier 2 : autres grandes villes (+8)
    "toulouse": 8, "bordeaux": 8, "nantes": 8,
    "strasbourg": 8, "rennes": 8, "grenoble": 8, "rouen": 8,
}

MAX_DAYS = 14

# LinkedIn guest API (no auth needed)
LINKEDIN_SEARCH_QUERIES = [
    "développeur java spring boot",
    "développeur fullstack",
    "ingénieur devops kubernetes",
    "développeur python django",
    "développeur react",
    "ingénieur intelligence artificielle",
    "software engineer",
]

# APEC queries (French engineers platform)
APEC_QUERIES = [
    "développeur java",
    "développeur fullstack",
    "devops cloud",
    "ingénieur python",
    "développeur react",
    "ingénieur IA",
]


def build_queries_from_prefs(prefs):
    """Build search queries from user preferences using Gemini LLM.

    Generates realistic job search queries that a human would type on
    job boards like Indeed, LinkedIn, WTTJ, France Travail.
    Falls back to simple heuristic if Gemini unavailable.
    """
    if not prefs:
        return None

    current_title = (prefs.get("current_title") or "").strip()
    titles_target = prefs.get("titles_target") or []
    skills_core = prefs.get("skills_core") or []
    contracts = prefs.get("contracts") or ["CDI"]

    if not titles_target and not skills_core and not current_title:
        return None

    # Try Gemini first
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            from google import genai
            client = genai.Client(api_key=gemini_key)

            prompt = f"""Tu es un expert en recherche d'emploi en France. Genere une liste de 12-15 requetes de recherche pour des job boards (Indeed, LinkedIn, WTTJ, France Travail).

Profil:
- Titre actuel: {current_title or 'Non specifie'}
- Postes vises: {', '.join(titles_target) if titles_target else 'Non specifie'}
- Competences principales: {', '.join(skills_core[:8]) if skills_core else 'Non specifie'}
- Contrats recherches: {', '.join(contracts)}

Regles:
- Genere des requetes realistes qu'un humain taperait sur un site d'emploi
- Inclus les titres de poste exacts vises
- Inclus des variantes (ex: "chef de projet SAP", "consultant SAP", "SAP manager")
- Inclus des requetes par competence cle quand ca fait sens comme titre (ex: "SAP" seul, "React developer")
- NE PAS generer de requetes absurdes (pas "developpeur UML", pas "ingenieur Agile")
- Une requete par ligne, sans numerotation, sans tiret, juste le texte

Retourne UNIQUEMENT la liste, rien d'autre."""

            response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
            raw = response.text.strip()
            queries = [q.strip().strip('-').strip('•').strip() for q in raw.split('\n') if q.strip() and len(q.strip()) > 2]
            queries = [q for q in queries if len(q) < 60][:18]

            if queries:
                print(f"  [LLM] Generated {len(queries)} queries: {', '.join(queries[:5])}...")
                return queries
        except Exception as e:
            print(f"  [LLM] Gemini query generation failed: {e}")

    # Fallback: smart heuristic without LLM — TITLES FIRST
    queries = []

    # 1. Exact target titles (most valuable — this is what the user wants)
    for title in titles_target:
        queries.append(title)

    # 2. Current title ONLY if it sounds like a job title (not "etudiant")
    _NOT_JOB_TITLES = {"etudiant", "student", "eleve", "diplome", "chercheur d'emploi", "en recherche"}
    if current_title and not any(w in current_title.lower() for w in _NOT_JOB_TITLES):
        queries.append(current_title)

    # 3. User skills as search queries — include anything specific enough
    #    Exclude only truly generic words that return garbage on job boards
    _NOT_SEARCHABLE = {
        "agile", "scrum", "uml", "jira", "git", "linux", "bash", "windows",
        "sql", "html", "css", "excel", "vba", "itil", "pmo", "ict",
        "architecture si", "transformation digitale", "prototypage",
        "design system", "content marketing", "copywriting",
        "analyse financiere", "comptabilite", "audit", "controle de gestion",
        "communication", "gestion de projet", "management", "leadership",
    }
    for skill in skills_core:
        sl = skill.lower().strip()
        # Include if: multi-word (specific) OR not in generic list
        if sl not in _NOT_SEARCHABLE and len(sl) > 2:
            queries.append(skill)

    # 4. Combine top skill with contract type for broader reach
    contract_labels = {"Alternance": "alternance", "Stage": "stage", "Freelance": "freelance"}
    for c in contracts:
        label = contract_labels.get(c)
        if label and titles_target:
            queries.append(f"{label} {titles_target[0]}")

    # Deduplicate preserving order
    seen = set()
    unique = []
    for q in queries:
        ql = q.lower()
        if ql not in seen:
            seen.add(ql)
            unique.append(q)

    return unique[:15] if unique else None


def _days_since(date_str):
    """Calcule le nombre de jours depuis une date ISO."""
    if not date_str:
        return 99
    try:
        posted = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(posted.tzinfo) if posted.tzinfo else datetime.now()
        return max(0, (now - posted).days)
    except (ValueError, TypeError):
        return 99


def _parse_relative_date(text):
    """Parse les dates relatives."""
    text = text.lower().strip()
    if "aujourd" in text or "just" in text or "heure" in text or "minute" in text:
        return 0
    if "hier" in text or "1 jour" in text:
        return 1
    match = re.search(r"(\d+)\s*jour", text)
    if match:
        return int(match.group(1))
    return 99


_EXP_TOO_SENIOR = re.compile(
    # === CATCH-ALL: any "4-10" + "ans/années" + "expérience" within 20 chars of each other ===
    # "5 années d'expérience", "5 ans d'expérience dans un poste", "tu as 5 ans d'exp"
    r'(?:4|5|6|7|8|9|10)\s*(?:ans?|années)\s+d.exp[eé]rience'
    r'|'
    # "expérience de 5 ans", "expérience : 5 ans"
    r'exp[eé]rience\s*.{0,15}(?:4|5|6|7|8|9|10)\s*(?:ans?|années)'
    r'|'
    # === PREFIX PATTERNS ===
    # "minimum 5 ans", "plus de 5 ans", "au moins 5 années"
    r'(?:minimum|au moins|plus de|au-delà de)\s*(?:4|5|6|7|8|9|10)\s*(?:ans?|années)'
    r'|'
    # "minimum 5 en tant que" (missing "ans" but clearly means years)
    r'(?:minimum|au moins|plus de)\s*(?:4|5|6|7|8|9|10)\s*(?:en tant que|dans |sur )'
    r'|'
    # === SUFFIX PATTERNS ===
    # "5+ ans", "6+ years"
    r'(?:4|5|6|7|8|9|10)\s*\+\s*(?:ans?|années|years)'
    r'|'
    # "5 ans minimum", "5 ans et plus", "5 ans requis"
    r'(?:4|5|6|7|8|9|10)\s*(?:ans?|années)\s*(?:minimum|et plus|requis)'
    r'|'
    # === RANGE PATTERNS ===
    # "4 à 6 ans", "4-6 ans", "5 à 10 ans"
    r'(?:4|5|6|7|8|9|10)\s*(?:à|-)\s*(?:5|6|7|8|9|10|15)\s*(?:ans?|années)'
    r'|'
    # === CONTEXT PATTERNS ===
    # "expérience ... de minimum 5", "justifier de 5 ans"
    r'(?:justifier?|disposer?|avoir)\s+(?:de\s+)?(?:4|5|6|7|8|9|10)\s*(?:ans?|années)'
    r'|'
    # === ENGLISH ===
    r'(?:4|5|6|7|8|9|10)\s*years?\s*(?:of\s*experience|experience|minimum)'
    r'|'
    r'experience\s*(?::|of)\s*(?:4|5|6|7|8|9|10)\+?\s*years',
    re.IGNORECASE,
)


# Skills Omar does NOT have — penalize offers that require these as primary stack
_ANTI_SKILLS = {
    # Hard anti (offer is centered on this tech, not Omar's profile)
    ".net": -12, "c#": -12, "asp.net": -12,
    "php": -15, "laravel": -12, "symfony": -12,
    "ruby": -15, "rails": -12,
    "scala": -12, "rust": -12, "golang": -12, "go ": -8,
    "swift": -15, "kotlin": -15, "flutter": -15, "react native": -5,
    "ios": -15, "android": -15,
    "salesforce": -15, "sap": -15, "cobol": -15,
    "mainframe": -15, "power bi": -8, "tableau": -8,
    "data engineer": -10, "data scientist": -12, "data analyst": -10,
    # Soft anti (not Omar's sweet spot, but not disqualifying)
    "angular": -3, "vue.js": -3, "vue ": -3,
    "aws": -2, "node.js": -2,
    "embedded": -10, "firmware": -10, "fpga": -10,
}

# Core stack groups — matching multiple skills in same group = coherent offer
_STACK_GROUPS = [
    {"java", "spring boot", "spring", "microservices", "api rest"},     # Java backend
    {"react", "typescript", "javascript", "graphql", "fullstack"},       # Frontend/Fullstack
    {"kubernetes", "docker", "devops", "ci/cd", "terraform", "ansible", "openshift"},  # DevOps
    {"python", "django", "ia", "llm", "rag", "genai", "ia générative"}, # Python/AI
]

# Red flags in description — signs the offer needs more experience than stated
_RED_FLAGS = re.compile(
    r'(?:'
    r'encadrer?\s+(?:une?\s+)?[eé]quipe|'
    r'manager?\s+\d+\s*(?:personnes|d[eé]velop)|'
    r'pilotage?\s+strat[eé]gique|'
    r'(?:5|6|7|8|10)\+?\s*ans?\s*(?:d.exp|minimum|requis|experience)|'
    r'experience?\s*(?:significative|confirm[eé]e|solide)\s*(?:en|de|du)|'
    r'expert(?:ise)?\s*(?:avanc[eé]e|reconnue|confirm[eé]e)'
    r')',
    re.IGNORECASE,
)


def _build_user_scoring(prefs):
    """Build scoring config from user preferences.

    prefs keys (all optional):
      - skills_core: list[str]       — high-weight skills (+10)
      - skills_secondary: list[str]  — medium-weight skills (+5)
      - skills_exclude: list[str]    — hard penalty skills (-15)
      - keywords_exclude: list[str]  — hard exclusion keywords
      - titles_target: list[str]     — title bonus keywords
      - experience_max: int          — block offers requiring more
      - seniority_block: bool        — block senior/lead/expert titles
      - cities: list[str]            — location priorities
    """
    if not prefs:
        return None

    cfg = {}

    # Build skill weights from user skills (core takes priority over secondary)
    profile_skills = {}
    for skill in (prefs.get("skills_secondary") or []):
        profile_skills[skill.lower()] = 5
    for skill in (prefs.get("skills_core") or []):
        profile_skills[skill.lower()] = 10  # overrides secondary if duplicate
    # Also add keywords as medium-weight (backwards compat with onboarding)
    for skill in (prefs.get("keywords") or []):
        s = skill.lower()
        if s not in profile_skills:
            profile_skills[s] = 7
    if profile_skills:
        cfg["profile_skills"] = profile_skills

    # Anti-skills
    anti_skills = {}
    for skill in (prefs.get("skills_exclude") or []):
        anti_skills[skill.lower()] = -15
    if anti_skills:
        cfg["anti_skills"] = anti_skills

    # Exclusion keywords
    if prefs.get("keywords_exclude"):
        cfg["keywords_exclude"] = [k.lower() for k in prefs["keywords_exclude"]]

    # Experience max
    if prefs.get("experience_max") is not None:
        cfg["experience_max"] = int(prefs["experience_max"])

    # Seniority block (default True)
    cfg["seniority_block"] = prefs.get("seniority_block", True)

    # Target titles + current title
    all_titles = list(prefs.get("titles_target") or [])
    current = (prefs.get("current_title") or "").strip()
    if current:
        all_titles.append(current)
    if all_titles:
        cfg["titles_target"] = [t.lower() for t in all_titles]

    # Cities → location priorities
    cities = prefs.get("cities") or []
    if cities:
        locations = {}
        for city in cities:
            c = city.lower()
            locations[c] = 15
            # Auto-add suburbs for Paris
            if c == "paris":
                for suburb in ["ile-de-france", "île-de-france", "la défense", "la defense",
                               "boulogne-billancourt", "issy-les-moulineaux", "nanterre",
                               "saint-denis", "levallois-perret", "rueil-malmaison",
                               "courbevoie", "puteaux", "clichy", "montreuil", "massy",
                               "guyancourt", "vélizy", "ivry-sur-seine", "saint-ouen"]:
                    locations[suburb] = 15
        cfg["locations"] = locations

    return cfg if cfg else None


def score_offer(offer, user_prefs=None):
    """Score une offre de 0-100.

    If user_prefs is provided, uses user-specific scoring config.
    Otherwise falls back to hardcoded Omar profile (admin mode).
    """
    cfg = _build_user_scoring(user_prefs) if user_prefs else None

    title = offer.get('title', '')
    desc = offer.get('description', '') or ''
    text = f"{title} {desc} {offer.get('company', '')}".lower()

    # ── Hard exclusions ──
    # User mode: ONLY use their exclusion list (they chose what to exclude)
    # Admin mode: use hardcoded list
    exclude_kws = cfg.get("keywords_exclude", []) if cfg else EXCLUDE_KEYWORDS
    for kw in exclude_kws:
        if kw in text:
            return -1

    # ── Seniority block ──
    seniority_block = (cfg or {}).get("seniority_block", True)
    if seniority_block:
        if _TITLE_SENIORITY.search(title):
            return -1
        if _DESC_SENIORITY.search(desc):
            return -1

    # ── Experience extraction from description ──
    exp_max_allowed = (cfg or {}).get("experience_max", 2)  # Omar default: 2 years max

    exp_min = offer.get("experience_min", 0) or 0

    # Find ALL year numbers near experience-related words in the text
    all_years = []
    # "5 a 10 ans", "3-5 ans", "2/3 ans"
    for m in re.finditer(r'(\d{1,2})\s*(?:à|a|-|/)\s*(\d{1,2})\s*(?:ans|an|années|years)', text):
        all_years.extend([int(m.group(1)), int(m.group(2))])
    # "5 ans d'experience", "5 ans minimum", "5 ans requis", "5 ans et plus", "5+ ans"
    for m in re.finditer(r'(\d{1,2})\s*(?:ans?|années)\s*(?:d.exp|minimum|requis|et plus|\+)', text):
        all_years.append(int(m.group(1)))
    # "experience de 5 ans", "experience ... 5 ans"
    for m in re.finditer(r'exp[eé]rience\s*.{0,25}?(\d{1,2})\s*(?:ans?|années)', text):
        all_years.append(int(m.group(1)))
    # "5 years experience", "5+ years of exp"
    for m in re.finditer(r'(\d{1,2})\+?\s*(?:ans?|years)\s*(?:of\s*)?exp', text):
        all_years.append(int(m.group(1)))
    # "minimum 5 ans", "au moins 5 ans", "plus de 5 ans"
    for m in re.finditer(r'(?:minimum|au moins|plus de)\s*(\d{1,2})\s*(?:ans?|années)', text):
        all_years.append(int(m.group(1)))
    # "justifiez de 5 ans", "justifier de 5 ans", "disposer de 5 ans"
    for m in re.finditer(r'(?:justifi\w+|disposer?|avoir)\s+(?:de?\s+)?(?:au moins\s+)?(\d{1,2})\s*(?:ans?|années)', text):
        all_years.append(int(m.group(1)))
    # "5 ans sur", "5 ans dans", "5 ans en" (experience context)
    for m in re.finditer(r'(\d{1,2})\s*(?:ans?|années)\s+(?:sur|dans|en|de)\s+', text):
        all_years.append(int(m.group(1)))

    # Filter out noise (0, 1-digit years that are clearly not experience like "24" for age)
    all_years = [y for y in all_years if 1 <= y <= 20]

    if all_years:
        desc_exp_max = max(all_years)
        desc_exp_min = min(all_years)
        if desc_exp_min > exp_min:
            exp_min = desc_exp_min
            offer["experience_min"] = exp_min
        # If ANY year number exceeds user's max → block
        if desc_exp_min > exp_max_allowed:
            return -1

    if exp_min and exp_min > exp_max_allowed:
        return -1

    # Also check _EXP_TOO_SENIOR for admin mode (no user prefs)
    if not cfg and _EXP_TOO_SENIOR.search(text):
        return -1

    # ── Positive: skill matching ──
    score = 0
    matched_skills = []
    skills = (cfg or {}).get("profile_skills") or PROFILE_SKILLS
    for skill, weight in skills.items():
        if skill in text:
            score += weight
            matched_skills.append(skill)

    # ── Negative: anti-skills ──
    anti = cfg.get("anti_skills", {}) if cfg else _ANTI_SKILLS
    for skill, penalty in anti.items():
        if skill in text:
            score += penalty

    # ── USER MODE: Domain relevance gate ──
    # If user has target titles/skills, the offer MUST relate to their domain
    if cfg:
        title_lower = title.lower()
        target_titles = cfg.get("titles_target") or []
        all_skills = list((cfg.get("profile_skills") or {}).keys())

        # Build domain keywords: significant words from titles + all skills
        _STOP_WORDS = {"de", "du", "le", "la", "les", "en", "et", "un", "une", "des", "pour", "par", "sur", "avec",
                        "senior", "junior", "chef", "manager", "consultant", "ingenieur", "developpeur",
                        "responsable", "lead", "expert", "projet", "stage", "alternance", "cdi", "cdd"}
        domain_words = set()
        for t in target_titles:
            for word in t.lower().split():
                if len(word) > 2 and word not in _STOP_WORDS:
                    domain_words.add(word)
        for s in all_skills:
            if len(s) > 2:
                domain_words.add(s.lower())

        if domain_words:
            text_match = any(w in text for w in domain_words)
            if not text_match:
                return -1

            title_match = any(w in title_lower for w in domain_words)
            if not title_match:
                score -= 25

    # ── Stack coherence bonus (admin mode only) ──
    if not cfg:
        matched_set = set(matched_skills)
        coherence_bonus = 0
        for group in _STACK_GROUPS:
            overlap = matched_set & group
            if len(overlap) >= 3:
                coherence_bonus = max(coherence_bonus, 15)
            elif len(overlap) >= 2:
                coherence_bonus = max(coherence_bonus, 8)
        score += coherence_bonus

    # ── Multi-match bonus ──
    n_matched = len(matched_skills)
    if n_matched >= 6:
        score += 20
    elif n_matched >= 4:
        score += 12
    elif n_matched >= 3:
        score += 6

    # ── Boost if junior / débutant ──
    for kw in BOOST_KEYWORDS:
        if kw in text:
            score += 7

    # ── Penalty for seniority words in description ──
    seniority_hits = 0
    for word in _SENIORITY_PENALTY_WORDS:
        if word in text:
            seniority_hits += 1
    if seniority_hits >= 3:
        return -1  # Too many seniority signals — definitely not junior
    score -= seniority_hits * 15

    # ── Experience bonus (admin: aggressive priority for low XP) ──
    if not cfg:
        # Omar mode: 0 XP gets massive boost, 3 XP barely passes
        if exp_min == 0:
            score += 30
        elif exp_min <= 1:
            score += 20
        elif exp_min <= 2:
            score += 10
        elif exp_min <= 3:
            score += 0  # no bonus, just allowed
    else:
        if exp_min == 0:
            score += 20
        elif exp_min <= 1:
            score += 15
        elif exp_min <= 2:
            score += 10
        elif exp_min <= exp_max_allowed:
            score += 3

    # ── Location bonus / filter ──
    location = offer.get("location", "").lower()
    location_bonus = 0
    locs = (cfg or {}).get("locations") or PRIORITY_LOCATIONS
    for loc, bonus in locs.items():
        if loc in location:
            location_bonus = max(location_bonus, bonus)
            break
    score += location_bonus
    offer["location_tier"] = "T1" if location_bonus >= 15 else "T2" if location_bonus >= 8 else "T3"

    # For user-specific scoring: exclude offers not in their selected cities
    if cfg and cfg.get("locations") and location_bonus == 0 and location:
        return -1

    # ── Short description penalty (can't fully verify XP) ──
    desc_len = len(offer.get("description", ""))
    if desc_len < 200:
        score -= 10
    elif desc_len < 400:
        score -= 5

    # ── Anonymous company penalty ──
    _GENERIC_CO = re.compile(r'^(confidentiel|entreprise|cabinet|esn|ssii|consulting|groupe|societe|client|recrutement)', re.IGNORECASE)
    company = offer.get("company", "")
    if not company or len(company) < 3 or _GENERIC_CO.match(company):
        score -= 5

    # ── ESN fast-hire boost (admin mode: Omar targets ESNs) ──
    if not cfg:
        _ESN_NAMES = ["capgemini", "sopra", "accenture", "cgi", "devoteam", "alten", "altran",
                       "atos", "onepoint", "wavestone", "extia", "davidson", "talan", "aubay",
                       "groupe open", "sii", "astek", "modis", "akkodis", "kyndryl", "ibm",
                       "ntt data", "blue soft", "hn services"]
        co_lower = company.lower()
        if any(esn in co_lower for esn in _ESN_NAMES):
            score += 8  # ESNs hire fast, priority for Omar

    # ── Freshness bonus ──
    days = offer.get("days_ago", 99)
    if days <= 1:
        score += 15
    elif days <= 3:
        score += 10
    elif days <= 7:
        score += 5
    elif days <= 14:
        score += 2

    # ── Title match bonus ──
    title_lower = title.lower()
    target_titles = (cfg or {}).get("titles_target")
    if target_titles:
        if any(t in title_lower for t in target_titles):
            score += 8
    else:
        # Default Omar title bonus (react/frontend boosted — quick to land)
        if any(k in title_lower for k in ["react", "frontend", "front-end", "front end", "front ", " front"]):
            score += 10
        elif any(k in title_lower for k in ["fullstack", "full stack", "full-stack"]):
            score += 8
        elif any(k in title_lower for k in ["java", "spring", "backend"]):
            score += 6
        elif any(k in title_lower for k in ["devops", "cloud", "sre", "platform"]):
            score += 6
        elif any(k in title_lower for k in ["python", "django", "ia", "intelligence artificielle"]):
            score += 6

    # ── Normalize ──
    score = min(100, max(0, score))

    # ── Junior/debutant boost (admin mode: Omar's priority) ──
    # Only boost if the offer is in Omar's tech domain (not finance, audit, HR, etc.)
    if not cfg:
        _omar_domain_re = re.compile(
            r'\b(?:java|spring|react|python|devops|fullstack|full.stack|frontend|front.end|backend|back.end|'
            r'cloud|kubernetes|docker|ci.cd|développeur|developpeur|ingénieur|ingenieur|software|'
            r'informatique|web\b|data\b|intelligence.artificielle|\bai\b|\bia\b|api\b|microservices|'
            r'consultant.technique|consultant.it|support.informatique|helpdesk|technicien|sre|'
            r'angular|typescript|node\.js|django|vue\.js|graphql|terraform)\b', re.IGNORECASE)
        is_tech_offer = bool(_omar_domain_re.search(text))

        _junior_signals = ["junior", "débutant", "debutant", "première expérience",
                           "premiere experience", "sortie d'école", "sortie d ecole",
                           "jeune diplômé", "jeune diplome", "0-1 an", "0-2 ans",
                           "debutant accepte", "sans experience", "profil debutant"]
        junior_in_title = any(s in title_lower for s in _junior_signals)
        junior_in_desc = sum(1 for s in _junior_signals if s in text)

        if is_tech_offer and junior_in_title and exp_min <= 1:
            score = 120  # absolute top tier
        elif is_tech_offer and junior_in_title:
            score = max(score, 115)
        elif is_tech_offer and junior_in_desc >= 2 and exp_min <= 1:
            score = max(score, 115)
        elif is_tech_offer and junior_in_desc >= 1 and exp_min <= 1:
            score = max(score, 110)
        elif is_tech_offer and junior_in_desc >= 1:
            score = max(score, 105)

    offer["score"] = score
    offer["matched_skills"] = matched_skills
    return score


# ============================================================
# WELCOME TO THE JUNGLE (Algolia API)
# ============================================================

def scrape_wttj(max_pages=3, queries=None):
    """Scrape WTTJ via l'API Algolia."""
    offers = []
    algolia_url = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
    algolia_headers = {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": ALGOLIA_API_KEY,
        "Content-Type": "application/json",
        "Referer": "https://www.welcometothejungle.com/",
        "Origin": "https://www.welcometothejungle.com",
    }

    seen_ids = set()

    for query in (queries or SEARCH_QUERIES):
        for page in range(0, max_pages):
            try:
                payload = {
                    "requests": [{
                        "indexName": ALGOLIA_INDEX,
                        "params": f"query={quote_plus(query)}&hitsPerPage=20&page={page}",
                    }]
                }
                resp = requests.post(algolia_url, json=payload, headers=algolia_headers, timeout=10)
                if resp.status_code != 200:
                    break

                data = resp.json()
                hits = data.get("results", [{}])[0].get("hits", [])
                if not hits:
                    break

                for hit in hits:
                    obj_id = hit.get("objectID", "")
                    if obj_id in seen_ids:
                        continue
                    seen_ids.add(obj_id)

                    # France only
                    offices = hit.get("offices", [])
                    if offices:
                        country = offices[0].get("country_code", "")
                        if country and country != "FR":
                            continue

                    published = hit.get("published_at", "")
                    days_ago = _days_since(published)

                    slug = hit.get("slug", "")
                    org = hit.get("organization", {}) if isinstance(hit.get("organization"), dict) else {}
                    org_slug = org.get("slug", "") or org.get("reference", "")
                    org_name = org.get("name", "")
                    city = offices[0].get("city", "") if offices else ""

                    offer_url = f"https://www.welcometothejungle.com/fr/companies/{org_slug}/jobs/{slug}" if org_slug and slug else ""

                    salary = ""
                    sal_min = hit.get("salary_minimum")
                    sal_max = hit.get("salary_maximum")
                    if sal_min and sal_max:
                        salary = f"{int(sal_min)}k-{int(sal_max)}k"
                    elif sal_min:
                        salary = f"{int(sal_min)}k+"

                    exp_min = hit.get("experience_level_minimum") or 0

                    # Construire la description enrichie pour le scoring
                    description_parts = []
                    if hit.get("summary"):
                        description_parts.append(hit["summary"])
                    for mission in (hit.get("key_missions") or []):
                        description_parts.append(mission)
                    description = " ".join(description_parts)

                    contract_type = hit.get("contract_type", "")
                    contract_label = {"full_time": "CDI", "temporary": "CDD", "internship": "Stage", "apprenticeship": "Alternance"}.get(contract_type, contract_type)

                    offers.append({
                        "source": "wttj",
                        "title": hit.get("name", ""),
                        "company": org_name,
                        "url": offer_url,
                        "location": city,
                        "contract": contract_label,
                        "days_ago": days_ago,
                        "salary": salary,
                        "description": description,
                        "remote": hit.get("remote", ""),
                        "experience_min": exp_min,
                    })

                time.sleep(0.3)
            except (requests.RequestException, json.JSONDecodeError):
                continue

    return offers


# ============================================================
# FRANCE TRAVAIL (JSON-LD + HTML)
# ============================================================

def scrape_francetravail(max_pages=3, queries=None, locations=None):
    """Scrape France Travail."""
    offers = []
    seen_urls = set()

    for query in (queries or SEARCH_QUERIES)[:15]:
        for page in range(1, max_pages + 1):
            try:
                params = {
                    "motsCles": query,
                    "typeContrat": "CDI,CDD",
                    "experience": "1",
                    "page": page,
                }
                url = f"https://candidat.francetravail.fr/offres/recherche?{urlencode(params)}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")

                # JSON-LD (meilleure source)
                for script in soup.find_all("script", type="application/ld+json"):
                    try:
                        data = json.loads(script.string)
                        items = data if isinstance(data, list) else [data]
                        for item in items:
                            if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                                continue

                            offer_url = item.get("url", "")
                            if offer_url in seen_urls:
                                continue
                            seen_urls.add(offer_url)

                            loc = item.get("jobLocation", {})
                            address = loc.get("address", {}) if isinstance(loc, dict) else {}
                            city = address.get("addressLocality", "") if isinstance(address, dict) else ""

                            hiring_org = item.get("hiringOrganization", {})
                            company = hiring_org.get("name", "") if isinstance(hiring_org, dict) else ""

                            description = _clean_html(item.get("description", ""))

                            offers.append({
                                "source": "francetravail",
                                "title": item.get("title", ""),
                                "company": company,
                                "url": offer_url,
                                "location": city,
                                "contract": item.get("employmentType", ""),
                                "days_ago": _days_since(item.get("datePosted", "")),
                                "salary": "",
                                "description": description[:1000],
                                "remote": "",
                                "experience_min": 0,
                            })
                    except (json.JSONDecodeError, KeyError, TypeError):
                        continue

                # Fallback: extraire les IDs d'offres depuis les liens
                for link in soup.select("a[href*='/offres/recherche/detail/']"):
                    href = link.get("href", "")
                    if not href.startswith("http"):
                        href = f"https://candidat.francetravail.fr{href}"
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    # Extraire l'ID pour scraper le détail plus tard
                    match = re.search(r"/detail/(\w+)", href)
                    if match:
                        offers.append({
                            "source": "francetravail",
                            "title": "",
                            "company": "",
                            "url": href,
                            "location": "",
                            "contract": "",
                            "days_ago": 99,
                            "salary": "",
                            "description": "",
                            "remote": "",
                            "experience_min": 0,
                            "_needs_detail": True,
                        })

                time.sleep(1)
            except requests.RequestException:
                continue

    return offers


def enrich_francetravail_offers(offers, max_detail=30):
    """Enrichit les offres sans description complète en scrapant le détail."""
    enriched = 0
    for offer in offers:
        if offer.get("source") not in ("francetravail", "linkedin"):
            continue
        # Enrich if: needs detail flag, or description is short/empty
        desc = offer.get("description", "")
        if offer.get("title") and len(desc) > 500 and not offer.get("_needs_detail"):
            continue
        if enriched >= max_detail:
            break

        detail = scrape_offer_detail(offer["url"])
        if "error" not in detail:
            if detail.get("title"):
                offer["title"] = detail["title"]
            if detail.get("company"):
                offer["company"] = detail["company"]
            if detail.get("location"):
                offer["location"] = detail["location"]
            if detail.get("description"):
                offer["description"] = detail["description"][:1000]
            if detail.get("date_posted"):
                offer["days_ago"] = _days_since(detail["date_posted"])
            elif detail.get("days_ago_override") is not None:
                offer["days_ago"] = detail["days_ago_override"]
            offer.pop("_needs_detail", None)
            enriched += 1
            time.sleep(0.5)

    return offers


# ============================================================
# INDEED (Chrome UC — bypass Cloudflare, extract mosaic JSON)
# ============================================================
# Uses undetected-chromedriver in headed mode (headless blocked by CF).
# Extracts window.mosaic JSON embedded in page source — no HTML parsing needed.
# Chrome 146 must be installed at the standard macOS path.
# ============================================================

INDEED_CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
INDEED_CHROME_VERSION = 146

# Compact query set — broad enough to cover full profile without excessive time
INDEED_QUERIES = [
    "développeur java spring",
    "développeur fullstack react",
    "développeur react",
    "développeur react native",
    "développeur python",
    "ingénieur devops",
    "software engineer",
    "développeur backend",
    "développeur IA",
]

INDEED_LOCATIONS = ["Paris", "Lyon", "Lille", "Marseille"]


def _indeed_extract_mosaic(page_source):
    """Extract job results from window.mosaic JSON embedded in Indeed page source."""
    import re as _re, json as _json
    m = _re.search(
        r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});\s*window',
        page_source, _re.DOTALL
    )
    if not m:
        return []
    try:
        data = _json.loads(m.group(1))
        return data.get('metaData', {}).get('mosaicProviderJobCardsModel', {}).get('results', [])
    except Exception:
        return []


def _indeed_parse_result(r, today):
    """Convert a mosaic result dict into our standard offer dict."""
    # days_ago
    pub_ms = r.get('pubDate')
    days_ago = 99
    if pub_ms:
        try:
            from datetime import timezone as _tz
            posted = datetime.fromtimestamp(pub_ms / 1000, tz=_tz.utc)
            days_ago = max(0, (today - posted).days)
        except Exception:
            pass

    # Contract
    job_types = r.get('jobTypes', []) or []
    types_lower = [t.lower() for t in job_types]
    if 'cdi' in types_lower:
        contract = 'CDI'
    elif 'cdd' in types_lower:
        contract = 'CDD'
    elif any(t in types_lower for t in ['temps plein', 'full-time']):
        contract = 'CDI'  # most "temps plein" on Indeed are CDI
    else:
        contract = ''

    # Salary
    sal = r.get('salarySnippet') or {}
    salary = sal.get('text', '').strip()

    # Remote
    remote_raw = (r.get('remoteWork') or '').lower()
    if 'full' in remote_raw or '100%' in remote_raw:
        remote = 'full'
    elif 'hybrid' in remote_raw or 'hybrid' in remote_raw or 'partiel' in remote_raw:
        remote = 'partial'
    else:
        remote = ''

    # Location tier
    loc = r.get('formattedLocation', '')
    loc_lower = loc.lower()
    dept_m = __import__('re').search(r'\((\d{2})\)', loc)
    dept = dept_m.group(1) if dept_m else ''
    if dept in {'75', '77', '78', '91', '92', '93', '94', '95'} or 'paris' in loc_lower:
        loc_tier = 'T1'
    elif any(c in loc_lower for c in ['lyon', 'marseille', 'lille', 'bordeaux', 'toulouse', 'nantes', 'strasbourg', 'montpellier']):
        loc_tier = 'T1'
    else:
        loc_tier = 'T2'

    # Description snippet (HTML → text)
    snippet_html = r.get('snippet', '') or ''
    description = BeautifulSoup(snippet_html, 'html.parser').get_text(' ', strip=True) if snippet_html else ''

    jk = r.get('jobkey', '')
    return {
        'source':        'indeed',
        'title':         r.get('title', '').strip(),
        'company':       r.get('company', '').strip(),
        'url':           f'https://fr.indeed.com/viewjob?jk={jk}',
        'location':      loc,
        'location_tier': loc_tier,
        'contract':      contract,
        'days_ago':      days_ago,
        'salary':        salary,
        'description':   description,
        'remote':        remote,
        'experience_min': 0,
    }


def scrape_indeed(max_pages=2, queries=None, locations=None):
    """Scrape Indeed FR via undetected-chromedriver (headed mode, bypass Cloudflare).

    Requires:
      - Google Chrome installed at INDEED_CHROME_PATH (macOS default)
      - pip install undetected-chromedriver selenium setuptools

    Returns [] gracefully if Chrome is not available or blocked.
    """
    try:
        import undetected_chromedriver as uc
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import importlib.util
        if importlib.util.find_spec('undetected_chromedriver') is None:
            raise ImportError("undetected_chromedriver not installed")
    except ImportError:
        print("  [Indeed] undetected-chromedriver not installed — pip install undetected-chromedriver setuptools")
        return []

    if not os.path.exists(INDEED_CHROME_PATH):
        print(f"  [Indeed] Chrome not found at {INDEED_CHROME_PATH}")
        return []

    from datetime import timezone as _tz
    today = datetime.now(tz=_tz.utc)

    offers = []
    seen_jks = set()
    driver = None
    blocked = False

    def _make_driver():
        opts = uc.ChromeOptions()
        opts.add_argument('--no-sandbox')
        opts.add_argument('--window-size=1280,900')
        opts.add_argument('--lang=fr-FR')
        opts.add_argument('--disable-notifications')
        opts.add_argument('--disable-popup-blocking')
        opts.binary_location = INDEED_CHROME_PATH
        d = uc.Chrome(options=opts, version_main=INDEED_CHROME_VERSION)
        d.set_page_load_timeout(30)
        return d

    try:
        driver = _make_driver()

        for location in (locations or INDEED_LOCATIONS):
            if blocked:
                break
            for query in (queries or INDEED_QUERIES)[:8]:
                if blocked:
                    break
                for page in range(max_pages):
                    start = page * 15
                    url = (
                        f"https://fr.indeed.com/emplois"
                        f"?q={quote_plus(query)}"
                        f"&l={quote_plus(location)}"
                        f"&fromage=7&sort=date&radius=30"
                        f"&start={start}"
                    )
                    retries = 0
                    while retries < 2:
                        try:
                            driver.get(url)
                            time.sleep(3.5 + page * 0.5)

                            title_lower = driver.title.lower()
                            if 'blocked' in title_lower or 'captcha' in title_lower:
                                print(f"  [Indeed] Blocked on {query}@{location} — stopping")
                                blocked = True
                                break

                            results = _indeed_extract_mosaic(driver.page_source)
                            if not results:
                                break

                            new_count = 0
                            for r in results:
                                jk = r.get('jobkey', '')
                                if not jk or jk in seen_jks:
                                    continue
                                seen_jks.add(jk)
                                offers.append(_indeed_parse_result(r, today))
                                new_count += 1

                            if new_count == 0:
                                break

                            next_btns = driver.find_elements(By.CSS_SELECTOR,
                                'a[data-testid="pagination-page-next"], [aria-label="Next Page"]')
                            if not next_btns:
                                break

                            time.sleep(1)
                            break  # success — exit retry loop

                        except Exception as e:
                            err_str = str(e)
                            if 'no such window' in err_str or 'target window already closed' in err_str or 'web view not found' in err_str:
                                print(f"  [Indeed] Window closed on {query}@{location} — reinitializing Chrome")
                                try:
                                    driver.quit()
                                except Exception:
                                    pass
                                try:
                                    driver = _make_driver()
                                    retries += 1
                                    time.sleep(2)
                                    continue  # retry same URL with new driver
                                except Exception as init_e:
                                    print(f"  [Indeed] Reinit failed: {init_e}")
                                    blocked = True
                                    break
                            else:
                                print(f"  [Indeed] Error on {query}@{location} p{page+1}: {e}")
                                break
                    else:
                        # max retries exhausted
                        break
                    if blocked:
                        break

        print(f"  [Indeed] {len(offers)} offres brutes extraites")

    except Exception as e:
        print(f"  [Indeed] Chrome init error: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass

    return offers


# ============================================================
# SCRAPE DETAIL D'UNE OFFRE
# ============================================================

def scrape_offer_detail(url):
    """Scrape le détail complet d'une offre."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}

        soup_raw = BeautifulSoup(resp.text, "html.parser")

        # JSON-LD
        for script in soup_raw.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    if isinstance(item, dict) and item.get("@type") == "JobPosting":
                        hiring_org = item.get("hiringOrganization", {})
                        loc = item.get("jobLocation", {})
                        address = loc.get("address", {}) if isinstance(loc, dict) else {}
                        return {
                            "url": url,
                            "title": item.get("title", ""),
                            "company": hiring_org.get("name", "") if isinstance(hiring_org, dict) else "",
                            "location": address.get("addressLocality", "") if isinstance(address, dict) else "",
                            "description": _clean_html(item.get("description", "")),
                            "date_posted": item.get("datePosted", ""),
                        }
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        # Fallback HTML — France Travail specific
        if "francetravail.fr" in url or "pole-emploi.fr" in url:
            title_el    = soup_raw.select_one(".title")
            loc_el      = soup_raw.select_one(".location")
            desc_el     = soup_raw.select_one(".description")
            meta_desc   = soup_raw.find("meta", attrs={"name": "description"})

            title    = title_el.get_text(strip=True) if title_el else ""
            raw_loc  = loc_el.get_text(strip=True) if loc_el else ""
            # strip dept code: "33 - BORDEAUX" → "Bordeaux"
            location = re.sub(r"^\d+\s*-\s*", "", raw_loc).title() if raw_loc else ""
            desc     = desc_el.get_text(separator=" ", strip=True)[:1500] if desc_el else ""

            # Extract days_ago and contract from meta description
            meta_content = meta_desc.get("content", "") if meta_desc else ""
            days_match = re.search(r"il y a (\d+) jour", meta_content)
            days_ago   = int(days_match.group(1)) if days_match else None

            # Extract company from description first paragraph if not in structured element
            company = ""
            if desc_el:
                p = desc_el.find("p")
                if p:
                    company = p.get_text(strip=True)[:80]

            return {
                "url": url,
                "title": title,
                "company": company,
                "location": location,
                "description": desc,
                "date_posted": "",
                "days_ago_override": days_ago,
            }

        # Generic fallback: texte brut
        for tag in soup_raw(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        main = soup_raw.select_one("main, article, .job-description, #job-description")
        if not main:
            main = soup_raw.find("body")
        text = main.get_text(separator="\n", strip=True) if main else ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        return {
            "url": url,
            "title": "",
            "company": "",
            "location": "",
            "description": "\n".join(lines)[:5000],
            "date_posted": "",
        }
    except requests.RequestException as e:
        return {"error": str(e)}


# ============================================================
# LINKEDIN (guest API — no auth)
# ============================================================

def scrape_linkedin(max_pages=2, queries=None):
    """Scrape LinkedIn jobs via guest API."""
    offers = []
    seen_ids = set()

    linkedin_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    for query in (queries or LINKEDIN_SEARCH_QUERIES):
        for page in range(max_pages):
            try:
                params = {
                    "keywords": query,
                    "location": "France",
                    "f_TPR": "r604800",   # last 7 days
                    "f_JT": "F",          # full-time
                    "start": page * 25,
                }
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?{urlencode(params)}"
                resp = requests.get(url, headers=linkedin_headers, timeout=15)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select("li")
                if not cards:
                    break

                for card in cards:
                    try:
                        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
                        if not link_el:
                            continue
                        href = link_el.get("href", "").split("?")[0].strip()
                        if not href:
                            continue

                        # Extract LinkedIn job ID to deduplicate
                        job_id_match = re.search(r"/jobs/view/(\d+)", href)
                        job_id = job_id_match.group(1) if job_id_match else href
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        title_el   = card.select_one(".base-search-card__title")
                        company_el = card.select_one(".base-search-card__subtitle")
                        loc_el     = card.select_one(".job-search-card__location")
                        date_el    = card.select_one("time")

                        title   = title_el.get_text(strip=True)   if title_el   else ""
                        company = company_el.get_text(strip=True)  if company_el else ""
                        location= loc_el.get_text(strip=True)      if loc_el     else ""

                        days_ago = 99
                        if date_el:
                            datetime_attr = date_el.get("datetime", "")
                            if datetime_attr:
                                days_ago = _days_since(datetime_attr)
                            else:
                                days_ago = _parse_relative_date(date_el.get_text(strip=True))

                        if not title:
                            continue

                        offers.append({
                            "source": "linkedin",
                            "title": title,
                            "company": company,
                            "url": href,
                            "location": location,
                            "contract": "",
                            "days_ago": days_ago,
                            "salary": "",
                            "description": f"{title} {company}",
                            "remote": "",
                            "experience_min": 0,
                            "_needs_detail": True,
                        })
                    except (AttributeError, TypeError):
                        continue

                time.sleep(1)
            except (requests.RequestException, Exception):
                continue

    return offers


# ============================================================
# CHOISIR LE SERVICE PUBLIC (fonction publique — JSON API)
# ============================================================

# IT-relevant keywords for CSP — covers both tech titles AND government IT vocabulary
# Government jobs rarely say "développeur fullstack". They say "chargé de mission numérique",
# "responsable applicatif", "expert SI", "analyste développeur", etc.
CSP_IT_KEYWORDS = [
    # Dev / ingénierie logicielle
    "développeur", "developpeur", "ingénieur", "ingenieur", "logiciel", "software",
    "fullstack", "full stack", "backend", "frontend", "python", "java", "react",
    # Infrastructure / réseau / cloud
    "devops", "cloud", "réseau", "reseau", "infrastructure", "sre", "plateforme",
    "virtualisation", "système", "systeme", "administrateur", "technicien",
    # SI / transformation / numérique (vocabulaire gouvernemental courant)
    "informatique", "numérique", "numerique", "digital",
    "système d'information", "systeme d'information", "si ", " si ", "référent si",
    "transformation numérique", "transformation digitale",
    "chargé de mission", "chef de projet", "chef de bureau",
    "responsable applicatif", "responsable si", "analyste",
    "concepteur", "expert technique", "architecte",
    "applicatif", "application", "erp", "crm",
    # Sécurité / data
    "cybersécurité", "cybersecurite", "sécurité informatique", "ssi", "ciso",
    "data", "ia ", "intelligence artificielle", "machine learning",
    # Opérations / support
    "exploitant", "support informatique", "support technique", "helpdesk",
    "centre de services", "itsm", "itil",
]

CSP_API_URL = "https://choisirleservicepublic.gouv.fr/wp-json/api/offer-list"
CSP_DETAIL_BASE = "https://choisirleservicepublic.gouv.fr"

# Departments accepted for CSP offers (Paris/IDF, Lyon, Lille, Marseille)
CSP_ALLOWED_DEPTS = {
    "75", "77", "78", "91", "92", "93", "94", "95",  # Paris + IDF
    "69",                                              # Lyon
    "59",                                              # Lille
    "13",                                              # Marseille / Bouches-du-Rhône
}
CSP_ALLOWED_CITIES = ["paris", "lyon", "lille", "marseille", "île-de-france", "ile-de-france"]


def _parse_csp_date(date_str):
    """Parse 'dd mois yyyy' → days_ago. e.g. '30 mars 2026'"""
    if not date_str:
        return 99
    months = {
        "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12,
    }
    m = re.match(r"(\d+)\s+(\w+)\s+(\d{4})", date_str.strip().lower())
    if m:
        try:
            day, month_name, year = int(m.group(1)), m.group(2), int(m.group(3))
            month = months.get(month_name)
            if month:
                from datetime import date
                posted = date(year, month, day)
                return max(0, (date.today() - posted).days)
        except (ValueError, TypeError):
            pass
    return 99


def scrape_csp(max_pages=8):
    """Scrape Choisir le Service Public — Numérique domain offers only.

    NOTE: The API always returns the same 20 most-recently-published offers
    regardless of pagination parameters. We call it once per unique session
    and deduplicate by reference. The `max_pages` parameter is kept for
    signature compatibility but the effective call count is limited.
    """
    offers = []
    seen_refs = set()

    csp_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://choisirleservicepublic.gouv.fr/nos-offres",
    }

    # The API ignores pagination and returns the same 20 items every call.
    # Call once per fresh session to get whatever is currently "live".
    for _ in range(1):
        try:
            session = requests.Session()
            session.get("https://choisirleservicepublic.gouv.fr/nos-offres/",
                        headers={**csp_headers, "Accept": "text/html"}, timeout=10)

            resp = session.post(
                CSP_API_URL,
                json={"page": 1, "per_page": 20},
                headers=csp_headers,
                timeout=15,
            )
            if resp.status_code != 200:
                break

            items = resp.json().get("items", [])
            if not items:
                break

            for item in items:
                ref = item.get("reference", "")
                if ref in seen_refs:
                    continue
                seen_refs.add(ref)

                title = item.get("title", "").strip()
                title_lower = title.lower()
                domain = item.get("domain", "")

                # Primary filter: Numérique domain (reliable) + IT keyword fallback
                is_it = (
                    domain == "Numérique"
                    or any(kw in title_lower for kw in CSP_IT_KEYWORDS)
                )
                if not is_it:
                    continue

                location_raw = item.get("localisation", "")
                location = re.sub(r"<[^>]+>", "", location_raw).strip()
                location_lower = location.lower()

                # Remote detection
                is_remote = any(k in title_lower + location_lower for k in
                                ["télétravail", "teletravail", "full remote", "100% remote", "100% télétravail"])

                # Location filter: only accepted cities/depts unless remote
                if not is_remote:
                    dept_match = re.search(r"\((\d{2,3})\)", location)
                    dept = dept_match.group(1) if dept_match else ""
                    city_ok = any(c in location_lower for c in CSP_ALLOWED_CITIES)
                    dept_ok = dept in CSP_ALLOWED_DEPTS
                    if not city_ok and not dept_ok:
                        continue

                offers.append({
                    "source": "csp",
                    "title": title,
                    "company": item.get("employeur", ""),
                    "url": item.get("url", ""),
                    "location": location,
                    "contract": "CDD",   # most contractuels are CDD-equivalent
                    "days_ago": _parse_csp_date(item.get("publication_date", "")),
                    "salary": "",
                    "description": f"{title} {item.get('employeur', '')}",
                    "remote": "",
                    "experience_min": 0,
                    "_needs_detail": True,
                })

        except (requests.RequestException, json.JSONDecodeError):
            pass

    return offers


def enrich_csp_offers(offers, max_detail=20):
    """Fetches JSON-LD detail for CSP offers."""
    enriched = 0
    detail_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }
    for offer in offers:
        if offer.get("source") != "csp" or not offer.get("_needs_detail"):
            continue
        if enriched >= max_detail:
            break
        try:
            resp = requests.get(offer["url"], headers=detail_headers, timeout=15)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string)
                    if ld.get("@type") == "JobPosting":
                        desc = _clean_html(ld.get("Description", ""))
                        skills = ld.get("skills", "")
                        exp_req = ld.get("experienceRequirements", "").lower()
                        offer["description"] = f"{desc} {skills}"[:1500]
                        if "débutant" in exp_req or "junior" in exp_req:
                            offer["experience_min"] = 0
                        elif "1 an" in exp_req or "1an" in exp_req:
                            offer["experience_min"] = 1
                        elif any(x in exp_req for x in ["2 ans", "3 ans"]):
                            offer["experience_min"] = 2
                        offer.pop("_needs_detail", None)
                        enriched += 1
                        break
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
            time.sleep(0.4)
        except requests.RequestException:
            continue
    return offers


# ============================================================
# APEC (French engineers platform — JSON API)
# ============================================================

APEC_API_URL = "https://www.apec.fr/cms/webservices/rechercheOffre"

# Location codes for APEC API (département numbers)
APEC_LIEUX = [
    75,   # Paris
    92,   # Hauts-de-Seine
    93,   # Seine-Saint-Denis
    94,   # Val-de-Marne
    69,   # Rhône (Lyon)
    59,   # Nord (Lille)
    13,   # Bouches-du-Rhône (Marseille)
    6,    # Alpes-Maritimes (Nice/Sophia)
    34,   # Hérault (Montpellier)
]

# Contract type codes: 101888 = CDI, 101887 = CDD
APEC_CONTRACT_MAP = {101888: "CDI", 101887: "CDD"}


_CITY_TO_DEPT = {
    "paris": [75, 92, 93, 94], "lyon": [69], "marseille": [13], "lille": [59],
    "toulouse": [31], "bordeaux": [33], "nantes": [44], "nice": [6],
    "montpellier": [34], "strasbourg": [67], "rennes": [35], "grenoble": [38],
}

def scrape_apec(max_pages=2, queries=None, locations=None):
    """Scrape APEC via their public JSON API (rechercheOffre)."""
    # Build APEC department codes from city names
    if locations:
        _apec_lieux = []
        for city in locations:
            depts = _CITY_TO_DEPT.get(city.lower(), [])
            _apec_lieux.extend(depts)
        _apec_lieux = list(set(_apec_lieux)) or APEC_LIEUX
    else:
        _apec_lieux = APEC_LIEUX

    offers = []
    seen_ids = set()

    apec_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://www.apec.fr/candidat/recherche-emploi.html/emploi",
        "Origin": "https://www.apec.fr",
    }

    for query in (queries or APEC_QUERIES):
        for page in range(max_pages):
            try:
                payload = {
                    "motsCles": query,
                    "lieux": _apec_lieux,
                    "sorts": [{"type": "DATE", "direction": "DESCENDING"}],
                    "pagination": {"startIndex": page * 20, "range": 20},
                }
                resp = requests.post(
                    APEC_API_URL,
                    json=payload,
                    headers=apec_headers,
                    timeout=15,
                )
                if resp.status_code != 200:
                    break

                data = resp.json()
                results = data.get("resultats", [])
                if not results:
                    break

                for item in results:
                    offer_id = str(item.get("numeroOffre", "") or item.get("id", ""))
                    if offer_id in seen_ids or not offer_id:
                        continue
                    seen_ids.add(offer_id)

                    title = item.get("intitule", "")
                    company = item.get("nomCommercial", "") or ""
                    location = item.get("lieuTexte", "")

                    date_str = item.get("datePublication", "")
                    days_ago = _days_since(date_str) if date_str else 99

                    contract_code = item.get("typeContrat")
                    contract = APEC_CONTRACT_MAP.get(contract_code, "")

                    salary = item.get("salaireTexte", "") or ""
                    description = _clean_html(item.get("texteOffre", ""))[:1000]

                    # Remote
                    remote_id = item.get("idNomTeletravail")
                    # 20949 = full remote, 20765 = partial, 20766 = occasional
                    remote = "full" if remote_id == 20949 else "partial" if remote_id in (20765, 20766) else ""

                    offer_url = f"https://www.apec.fr/candidat/recherche-emploi.html/emploi/detail-offre/{offer_id}"

                    # Location tier
                    loc_lower = location.lower()
                    if any(c in loc_lower for c in ["paris", "75", "92", "93", "94"]):
                        loc_tier = "T1"
                    elif any(c in loc_lower for c in ["lyon", "69", "lille", "59", "marseille", "13", "nice", "06", "montpellier", "34"]):
                        loc_tier = "T1"
                    else:
                        loc_tier = "T2"

                    offers.append({
                        "source": "apec",
                        "title": title,
                        "company": company,
                        "url": offer_url,
                        "location": location,
                        "location_tier": loc_tier,
                        "contract": contract,
                        "days_ago": days_ago,
                        "salary": salary,
                        "description": description,
                        "remote": remote,
                        "experience_min": 0,
                    })

                time.sleep(0.5)
            except (requests.RequestException, json.JSONDecodeError, KeyError):
                continue

    return offers


def enrich_apec_offers(offers, max_detail=100):
    """Enrich APEC offers by fetching full description from detail API (parallelized)."""
    from concurrent.futures import ThreadPoolExecutor

    to_enrich = []
    for offer in offers:
        if offer.get("source") != "apec":
            continue
        if len(offer.get("description", "")) > 500:
            continue
        url = offer.get("url", "")
        offer_id = url.split("/")[-1] if "/" in url else ""
        if offer_id:
            to_enrich.append((offer, offer_id))
        if len(to_enrich) >= max_detail:
            break

    if not to_enrich:
        return offers

    def _fetch_apec_detail(item):
        offer, offer_id = item
        try:
            r = requests.get(
                f"https://www.apec.fr/cms/webservices/offre/public?numeroOffre={offer_id}",
                headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                full_desc = data.get("texteHtml", "") or data.get("texte", "") or ""
                if full_desc:
                    offer["description"] = _clean_html(full_desc)[:2000]
        except Exception:
            pass

    print(f"  Enriching {len(to_enrich)} APEC offers in parallel...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        pool.map(_fetch_apec_detail, to_enrich)

    return offers


# ============================================================
# ADZUNA (aggregates Indeed, Reed, Monster, 50+ French boards)
# ============================================================
# Free API: register at https://developer.adzuna.com → app_id + app_key
# Free tier: 250 req/month — enough for ~8 scans/day with our query set
# Credentials stored in .env: ADZUNA_APP_ID and ADZUNA_APP_KEY
# ============================================================

ADZUNA_APP_ID  = os.environ.get("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY", "")
ADZUNA_API_URL = "https://api.adzuna.com/v1/api/jobs/fr/search/{page}"

# Compact query set — wide enough to cover the full profile without burning quota
ADZUNA_QUERIES = [
    "développeur java spring",
    "développeur fullstack react",
    "développeur python",
    "ingénieur devops kubernetes",
    "développeur backend",
    "software engineer",
    "développeur IA LLM",
    "ingénieur logiciel",
    "développeur react typescript",
    "consultant développement",
]

# French metro areas to target (Adzuna uses free-text location)
ADZUNA_LOCATIONS = ["Paris", "Lyon", "Lille", "Marseille"]


def scrape_adzuna(max_pages=1, queries=None, locations=None):
    """Scrape Adzuna API — aggregates Indeed + 50+ French job boards.

    Returns [] silently if credentials are not configured (ADZUNA_APP_ID / ADZUNA_APP_KEY).
    Register free at https://developer.adzuna.com to get credentials.
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        print("  [Adzuna] No credentials — set ADZUNA_APP_ID / ADZUNA_APP_KEY in .env to enable")
        return []

    offers = []
    seen_ids = set()
    today = datetime.now().date()

    adzuna_headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
    }

    for location in (locations or ADZUNA_LOCATIONS):
        for query in (queries or ADZUNA_QUERIES):
            for page in range(1, max_pages + 1):
                try:
                    resp = requests.get(
                        ADZUNA_API_URL.format(page=page),
                        params={
                            "app_id":          ADZUNA_APP_ID,
                            "app_key":         ADZUNA_APP_KEY,
                            "results_per_page": 50,
                            "what":            query,
                            "where":           location,
                            "distance":        30,
                            "sort_by":         "date",
                            "max_days_old":    7,
                            "content-type":    "application/json",
                        },
                        headers=adzuna_headers,
                        timeout=15,
                    )

                    if resp.status_code == 401:
                        print("  [Adzuna] AUTH_FAIL — check ADZUNA_APP_ID / ADZUNA_APP_KEY")
                        return offers
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    results = data.get("results", [])
                    if not results:
                        break

                    for job in results:
                        job_id = str(job.get("id", ""))
                        if job_id in seen_ids:
                            continue
                        seen_ids.add(job_id)

                        # Parse creation date → days_ago
                        created = job.get("created", "")
                        days_ago = 99
                        if created:
                            try:
                                posted = datetime.fromisoformat(created[:10]).date()
                                days_ago = max(0, (today - posted).days)
                            except ValueError:
                                pass

                        # Salary
                        salary = ""
                        sal_min = job.get("salary_min")
                        sal_max = job.get("salary_max")
                        if sal_min and sal_max:
                            salary = f"{int(sal_min/1000)}-{int(sal_max/1000)}k€"
                        elif sal_min:
                            salary = f"{int(sal_min/1000)}k€+"

                        # Contract type — Adzuna uses "permanent" / "contract" / "part_time"
                        contract_raw = (job.get("contract_type") or "").lower()
                        contract = "CDI" if "permanent" in contract_raw else "CDD" if "contract" in contract_raw else ""

                        # Location tier
                        location_label = job.get("location", {}).get("display_name", location)
                        location_lower = location_label.lower()
                        if any(c in location_lower for c in ["paris", "île-de-france", "hauts-de-seine", "seine-saint-denis", "val-de-marne"]):
                            loc_tier = "T1"
                        elif any(c in location_lower for c in ["lyon", "marseille", "lille", "bordeaux", "toulouse", "nantes", "strasbourg"]):
                            loc_tier = "T1"
                        else:
                            loc_tier = "T2"

                        # Source attribution — Adzuna often knows the original board
                        redirect_url = job.get("redirect_url", "")
                        adref = job.get("adref", "")

                        offers.append({
                            "source":         "adzuna",
                            "title":          job.get("title", "").strip(),
                            "company":        job.get("company", {}).get("display_name", ""),
                            "url":            redirect_url or f"https://www.adzuna.fr/emplois/{adref}",
                            "location":       location_label,
                            "location_tier":  loc_tier,
                            "contract":       contract,
                            "days_ago":       days_ago,
                            "salary":         salary,
                            "description":    _clean_html(job.get("description", "")),
                            "remote":         "",
                            "experience_min": 0,
                        })

                    time.sleep(0.3)

                except (requests.RequestException, json.JSONDecodeError, KeyError):
                    continue

    return offers


# ============================================================
# PMEJOB (HTML scraping + JSON-LD detail)
# ============================================================

PMEJOB_BASE = "https://www.pmejob.fr"
PMEJOB_QUERIES = [
    "Informatique",
]


def scrape_pmejob(max_pages=5):
    """Scrape PMEjob.fr — listing pages then enrich via JSON-LD detail pages."""
    offers = []
    seen_urls = set()

    for fonction in PMEJOB_QUERIES:
        for page in range(1, max_pages + 1):
            try:
                url = f"{PMEJOB_BASE}/recherche-emploi.php?fonction={quote_plus(fonction)}&region=&p={page}"
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    break

                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.select("h3 > a[href*='offre-emploi-']")
                if not links:
                    break

                for a in links:
                    href = a.get("href", "")
                    if not href:
                        continue
                    if not href.startswith("http"):
                        href = f"{PMEJOB_BASE}/{href}"
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)

                    title = a.get_text(strip=True)

                    offers.append({
                        "source": "pmejob",
                        "title": title,
                        "company": "",
                        "url": href,
                        "location": "",
                        "contract": "",
                        "days_ago": 99,
                        "salary": "",
                        "description": "",
                        "remote": "",
                        "experience_min": 0,
                        "_needs_detail": True,
                    })

                time.sleep(0.5)
            except requests.RequestException:
                continue

    return offers


def enrich_pmejob_offers(offers, max_detail=40):
    """Enrich PMEjob offers by scraping JSON-LD from detail pages."""
    enriched = 0
    for offer in offers:
        if offer.get("source") != "pmejob" or not offer.get("_needs_detail"):
            continue
        if enriched >= max_detail:
            break

        try:
            resp = requests.get(offer["url"], headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # JSON-LD (primary source)
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string, strict=False)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if not isinstance(item, dict) or item.get("@type") != "JobPosting":
                            continue

                        hiring_org = item.get("hiringOrganization", {})
                        loc = item.get("jobLocation", {})
                        address = loc.get("address", {}) if isinstance(loc, dict) else {}

                        offer["title"] = item.get("title", offer["title"]).replace(" - CDI", "").replace(" - CDD", "").replace(" - Independant", "").strip()
                        offer["company"] = hiring_org.get("name", "") if isinstance(hiring_org, dict) else ""
                        raw_loc = address.get("addressLocality", "") if isinstance(address, dict) else ""
                        offer["location"] = raw_loc.title() if raw_loc else ""
                        offer["description"] = _clean_html(item.get("description", ""))[:1000]

                        # Date
                        date_posted = item.get("datePosted", "")
                        if date_posted:
                            offer["days_ago"] = _days_since(date_posted)

                        # Contract
                        emp_type = (item.get("employmentType") or "").upper()
                        if "FULL_TIME" in emp_type:
                            offer["contract"] = "CDI"
                        elif "TEMPORARY" in emp_type or "CONTRACT" in emp_type:
                            offer["contract"] = "CDD"

                        # Experience
                        exp_req = item.get("experienceRequirements", {})
                        if isinstance(exp_req, dict):
                            months = exp_req.get("monthsOfExperience", "")
                            if months:
                                try:
                                    offer["experience_min"] = int(months) // 12
                                except (ValueError, TypeError):
                                    pass

                        offer.pop("_needs_detail", None)
                        break
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue

            # Fallback: parse date from page text if JSON-LD didn't have it
            if offer.get("days_ago", 99) == 99:
                page_text = soup.get_text()
                date_match = re.search(r"publi[ée]+e?\s+le\s+(\d{2})-(\d{2})-(\d{4})", page_text, re.IGNORECASE)
                if date_match:
                    try:
                        d, m, y = date_match.groups()
                        posted = datetime(int(y), int(m), int(d))
                        offer["days_ago"] = max(0, (datetime.now() - posted).days)
                    except ValueError:
                        pass

            enriched += 1
            time.sleep(0.3)
        except requests.RequestException:
            continue

    return offers


# ============================================================
# HELLOWORK (JSON-LD from detail pages)
# ============================================================

def scrape_hellowork(max_pages=2, queries=None, locations=None):
    """Scrape HelloWork.com — search pages for URLs, detail pages for JSON-LD."""
    offers = []
    seen_urls = set()
    search_queries = queries or SEARCH_QUERIES[:10]
    search_locations = locations or ["Paris"]

    for query in search_queries[:8]:
        for location in search_locations[:3]:
            for page in range(1, max_pages + 1):
                try:
                    url = f"https://www.hellowork.com/fr-fr/emploi/recherche.html?k={quote_plus(query)}&l={quote_plus(location)}&p={page}"
                    resp = requests.get(url, headers=HEADERS, timeout=15)
                    if resp.status_code != 200:
                        break

                    soup = BeautifulSoup(resp.text, "html.parser")
                    # Find offer links
                    links = soup.find_all("a", href=re.compile(r"/fr-fr/emplois/\d+\.html"))
                    if not links:
                        break

                    for link in links:
                        href = link.get("href", "")
                        if not href.startswith("http"):
                            href = f"https://www.hellowork.com{href}"
                        if href in seen_urls:
                            continue
                        seen_urls.add(href)

                        offers.append({
                            "source": "hellowork",
                            "title": "",
                            "company": "",
                            "url": href,
                            "location": location,
                            "contract": "",
                            "days_ago": 99,
                            "salary": "",
                            "description": "",
                            "remote": "",
                            "experience_min": 0,
                            "_needs_detail": True,
                        })

                    time.sleep(0.5)
                except requests.RequestException:
                    continue

    return offers


def enrich_hellowork_offers(offers, max_detail=30):
    """Enrich HelloWork offers from detail page JSON-LD."""
    from concurrent.futures import ThreadPoolExecutor
    to_enrich = [(o, o["url"]) for o in offers if o.get("source") == "hellowork" and o.get("_needs_detail")][:max_detail]
    if not to_enrich:
        return offers

    def _fetch(item):
        offer, url = item
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code != 200:
                return
            soup = BeautifulSoup(r.text, "html.parser")
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string, strict=False)
                    if not isinstance(data, dict) or data.get("@type") != "JobPosting":
                        continue
                    offer["title"] = data.get("title", "")
                    org = data.get("hiringOrganization", {})
                    offer["company"] = org.get("name", "") if isinstance(org, dict) else ""
                    loc = data.get("jobLocation", {})
                    addr = loc.get("address", {}) if isinstance(loc, dict) else {}
                    offer["location"] = addr.get("addressLocality", "") if isinstance(addr, dict) else ""
                    offer["description"] = _clean_html(data.get("description", ""))[:2000]
                    offer["days_ago"] = _days_since(data.get("datePosted", ""))
                    emp = (data.get("employmentType") or "").upper()
                    if "FULL_TIME" in emp:
                        offer["contract"] = "CDI"
                    elif "TEMPORARY" in emp or "CONTRACT" in emp:
                        offer["contract"] = "CDD"
                    offer.pop("_needs_detail", None)
                    break
                except (json.JSONDecodeError, TypeError):
                    continue
        except requests.RequestException:
            pass

    print(f"  Enriching {len(to_enrich)} HelloWork offers...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        pool.map(_fetch, to_enrich)

    return offers


# ============================================================
# UTILS
# ============================================================

def _clean_html(html_text):
    if not html_text:
        return ""
    return BeautifulSoup(html_text, "html.parser").get_text(separator="\n", strip=True)


def _deduplicate(offers):
    """Déduplique par URL, puis par titre+entreprise similaire."""
    seen_urls = set()
    seen_titles = set()
    unique = []
    for o in offers:
        url = o.get("url", "")
        if url:
            if url in seen_urls:
                continue
            seen_urls.add(url)

        # Déduplique aussi par titre+company (même offre sur plusieurs queries)
        key = f"{o.get('title', '').lower().strip()}|{o.get('company', '').lower().strip()}"
        if key in seen_titles and key != "|":
            continue
        seen_titles.add(key)

        unique.append(o)
    return unique


def search_all(max_pages=2, enrich=True, user_prefs=None):
    """
    Lance la recherche sur toutes les sources EN PARALLELE.
    Score et filtre les résultats.
    If user_prefs is provided, generates queries from user preferences.
    Otherwise uses hardcoded Omar queries (admin mode).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Build queries from user preferences if provided
    q = build_queries_from_prefs(user_prefs) if user_prefs else None
    # Build location list from user cities
    user_cities = (user_prefs or {}).get("cities")
    locs = user_cities if user_cities else None
    mode = "personnalise" if q else "admin (Omar)"

    print("=" * 60)
    print(f"  SCAN DES OFFRES — Mode {mode}")
    if q:
        print(f"  Queries: {', '.join(q[:5])}{'...' if len(q) > 5 else ''}")
    if locs:
        print(f"  Villes: {', '.join(locs)}")
    print("=" * 60)

    # 1. Scrape all sources IN PARALLEL (API-based scrapers)
    results = {}

    def _run(name, fn, **kwargs):
        try:
            return name, fn(**kwargs)
        except Exception as e:
            print(f"  [{name}] Error: {e}")
            return name, []

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [
            pool.submit(_run, "WTTJ", scrape_wttj, max_pages=max_pages, queries=q),
            pool.submit(_run, "France Travail", scrape_francetravail, max_pages=max_pages, queries=q, locations=locs),
            pool.submit(_run, "LinkedIn", scrape_linkedin, max_pages=max_pages, queries=q),
            pool.submit(_run, "CSP", scrape_csp, max_pages=8),
            pool.submit(_run, "Adzuna", scrape_adzuna, max_pages=1, queries=q, locations=locs),
            pool.submit(_run, "APEC", scrape_apec, max_pages=2, queries=q, locations=locs),
            pool.submit(_run, "PMEjob", scrape_pmejob, max_pages=5),
            pool.submit(_run, "HelloWork", scrape_hellowork, max_pages=2, queries=q, locations=locs),
        ]
        for future in as_completed(futures):
            name, offers = future.result()
            results[name] = offers
            print(f"  [{name}] {len(offers)} offres")

    # Indeed disabled — Adzuna already aggregates Indeed offers via API (no Chrome needed)
    # To re-enable: uncomment and run with Chrome installed
    # print("  [Indeed] Starting Chrome scraper...")
    # indeed = scrape_indeed(max_pages=1, queries=q, locations=locs)
    # results["Indeed"] = indeed
    # print(f"  [Indeed] {len(indeed)} offres")

    # 2. Déduplique
    all_raw = []
    for name, offers in results.items():
        all_raw.extend(offers)
    all_offers = _deduplicate(all_raw)
    print(f"\n[→] Déduplication → {len(all_offers)} offres uniques")

    # 3. Enrichir TOUTES les offres avec descriptions courtes (< 500 chars)
    if enrich:
        # Mark all short-description offers as needing enrichment
        for o in all_offers:
            if len(o.get("description", "")) < 500 and not o.get("_needs_detail"):
                o["_needs_detail"] = True

        needs_enrichment = sum(1 for o in all_offers if o.get("_needs_detail"))
        print(f"  {needs_enrichment} offres a enrichir (descriptions courtes ou manquantes)...")
        if needs_enrichment > 0:
            all_offers = enrich_francetravail_offers(all_offers, max_detail=150)
            all_offers = enrich_csp_offers(all_offers, max_detail=20)
            all_offers = enrich_pmejob_offers(all_offers, max_detail=40)
            print(f"  Enrichissement APEC (descriptions completes)...")
            all_offers = enrich_apec_offers(all_offers, max_detail=100)
            print(f"  Enrichissement HelloWork...")
            all_offers = enrich_hellowork_offers(all_offers, max_detail=30)

    # 4. Score et filtre
    print("[4/4] Scoring et filtrage...")
    scored = []
    excluded = 0
    for offer in all_offers:
        s = score_offer(offer, user_prefs=user_prefs)
        if s >= 0:
            scored.append(offer)
        else:
            excluded += 1

    # Filtrer < 14 jours, score > 0, contrats autorisés
    if user_prefs and user_prefs.get("contracts"):
        ALLOWED_CONTRACTS = {c.lower() for c in user_prefs["contracts"]}
        if "cdi" in ALLOWED_CONTRACTS or "cdd" in ALLOWED_CONTRACTS:
            ALLOWED_CONTRACTS.add("")
        if "freelance" in ALLOWED_CONTRACTS:
            ALLOWED_CONTRACTS.update(["independant", "mission", "interim", "portage", "freelance"])
    else:
        ALLOWED_CONTRACTS = {"cdi", "cdd", ""}
    recent = [o for o in scored
              if o.get("days_ago", 99) <= MAX_DAYS
              and o.get("score", 0) > 0
              and o.get("contract", "").lower() in ALLOWED_CONTRACTS]

    # Tri : score (relevance) d'abord, puis XP basse + récent en tiebreaker
    # Score bands: 80-100 = top, 50-79 = bon, 20-49 = possible, 0-19 = faible
    def sort_key(o):
        days = o.get("days_ago", 99)
        score = o.get("score", 0)
        loc_tier = o.get("location_tier", "T3")
        tier_val = {"T1": 0, "T2": 1, "T3": 2}.get(loc_tier, 2)

        # Score band (0 = best)
        if score >= 80:
            score_band = 0
        elif score >= 50:
            score_band = 1
        elif score >= 20:
            score_band = 2
        else:
            score_band = 3

        # XP bucket: 0 = débutant (best), 1 = 1an, 2 = 2-3ans
        exp = o.get("experience_min", 0)
        exp_bucket = 0 if exp == 0 else 1 if exp <= 1 else 2

        # Within same score band: favor low XP, then recent, then location
        return (score_band, exp_bucket, days, tier_val, -score)

    recent.sort(key=sort_key)

    # Fallback
    if len(recent) < 5:
        scored.sort(key=sort_key)
        recent = [o for o in scored if o.get("score", 0) > 0][:50]

    print(f"\n{'=' * 60}")
    print(f"Total brut : {len(all_offers)} | Exclus : {excluded}")
    print(f"Scorés : {len(scored)} | Pertinents (<{MAX_DAYS}j) : {len(recent)}")
    t1 = sum(1 for o in recent if o.get("location_tier") == "T1")
    t2 = sum(1 for o in recent if o.get("location_tier") == "T2")
    t3 = sum(1 for o in recent if o.get("location_tier") == "T3")
    src_counts = {}
    for o in recent:
        s = o.get("source", "?")
        src_counts[s] = src_counts.get(s, 0) + 1
    src_str = " | ".join(f"{s.upper()}: {n}" for s, n in sorted(src_counts.items()))
    print(f"Sources : {src_str}")
    print(f"Localisation : {t1} Paris/Lyon/Sud | {t2} Autres grandes villes | {t3} Reste")
    print(f"{'=' * 60}")

    return recent
