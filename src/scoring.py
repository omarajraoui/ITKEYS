"""
Scoring V2 — Multi-dimension job evaluation engine.
Replaces the old keyword-matching score_offer function.

Each offer is evaluated across multiple dimensions, producing:
- A recommendation (STRONG_APPLY, APPLY, STRETCH, LOW_PRIORITY, REJECT)
- Dimension scores (0-100 each)
- Matched/missing skills
- Human-readable reasoning
"""

import re
import os

# Recommendation levels
STRONG_APPLY = "STRONG_APPLY"  # Perfect match, apply immediately
APPLY = "APPLY"                # Good match, worth applying
STRETCH = "STRETCH"            # Possible but risky (higher XP, partial skill match)
LOW_PRIORITY = "LOW_PRIORITY"  # Weak match, only if desperate
REJECT = "REJECT"              # Don't show

# Experience patterns for extraction
_EXP_PATTERNS = [
    re.compile(r'(\d+)\s*(?:à|a|-|/)\s*(\d+)\s*(?:ans|an|années|years)', re.IGNORECASE),
    re.compile(r'(\d+)\s*(?:ans?|années)\s*(?:d.exp|minimum|requis|et plus|\+)', re.IGNORECASE),
    re.compile(r'exp[eé]rience\s*.{0,25}?(\d+)\s*(?:ans?|années)', re.IGNORECASE),
    re.compile(r'(?:minimum|au moins|plus de)\s*(\d+)\s*(?:ans?|années)', re.IGNORECASE),
    re.compile(r'(?:justifi\w+|disposer?|avoir)\s+(?:de?\s+)?(?:au moins\s+)?(\d+)\s*(?:ans?|années)', re.IGNORECASE),
    re.compile(r'(\d+)\s*(?:ans?|années)\s+(?:sur|dans|en|de)\s+', re.IGNORECASE),
    re.compile(r'(\d+)\+?\s*(?:ans?|years)\s*(?:of\s*)?exp', re.IGNORECASE),
]

# Seniority signals in title
_TITLE_SENIORITY = re.compile(
    r'\b(?:s[eé]nior|sr\b|confirm[eé]|exp[eé]riment[eé]|'
    r'tech(?:nical)?\s*lead(?:er)?|lead\s*(?:dev|backend|frontend|fullstack|developer|data|cloud|mobile|platform|software|sre)|'
    r'principal\s*(?:engineer|developer)|staff\s*engineer|expert\b|architecte\b|responsable\b)',
    re.IGNORECASE,
)

# Seniority signals in description
_SENIORITY_WORDS = [
    "confirmé", "confirmee", "confirmes", "expérimenté", "experimentee",
    "expérience significative", "experience significative",
    "expérience solide", "experience solide",
    "profils confirmés", "profil confirmé",
    "référent technique", "referent technique",
    "encadrement", "management d'équipe",
]

# Junior signals
_JUNIOR_SIGNALS = [
    "junior", "débutant", "debutant", "première expérience",
    "premiere experience", "sortie d'école", "sortie d ecole",
    "jeune diplômé", "jeune diplome", "0-1 an", "0-2 ans",
    "debutant accepte", "sans experience", "profil debutant",
]


def extract_experience_years(text):
    """Extract all experience year numbers from text. Returns list of ints."""
    all_years = []
    for pattern in _EXP_PATTERNS:
        for m in pattern.finditer(text):
            groups = [int(g) for g in m.groups() if g]
            all_years.extend(groups)
    return [y for y in all_years if 1 <= y <= 20]


def evaluate_offer(offer, user_prefs):
    """
    Evaluate a job offer against user preferences.
    Returns a dict with recommendation, dimensions, skills, and reasoning.
    """
    title = offer.get("title", "")
    desc = offer.get("description", "") or ""
    company = offer.get("company", "") or ""
    location = offer.get("location", "") or ""
    contract = offer.get("contract", "") or ""
    text = f"{title} {desc} {company}".lower()
    title_lower = title.lower()

    # User preferences
    skills_core = [s.lower() for s in (user_prefs.get("skills_core") or [])]
    skills_secondary = [s.lower() for s in (user_prefs.get("skills_secondary") or [])]
    skills_exclude = [s.lower() for s in (user_prefs.get("skills_exclude") or [])]
    titles_target = [t.lower() for t in (user_prefs.get("titles_target") or [])]
    current_title = (user_prefs.get("current_title") or "").lower()
    exp_max = user_prefs.get("experience_max", 3)
    cities = [c.lower() for c in (user_prefs.get("cities") or [])]
    contracts = [c.lower() for c in (user_prefs.get("contracts") or [])]
    seniority_block = user_prefs.get("seniority_block", True)
    keywords_exclude = [k.lower() for k in (user_prefs.get("keywords_exclude") or [])]

    # Initialize dimensions
    dims = {
        "roleFit": 0,
        "skillFit": 0,
        "experienceFit": 0,
        "seniorityRisk": 0,
        "locationFit": 0,
        "contractFit": 0,
    }
    matched_skills = []
    missing_skills = []
    reasons_apply = []
    reasons_not = []

    # ═══ HARD REJECTIONS ═══

    # Excluded keywords
    for kw in keywords_exclude:
        if kw in text:
            return _make_result(REJECT, 0, dims, [], [], [], [f"Mot-cle exclu: '{kw}'"])

    # Excluded skills (anti-skills)
    for skill in skills_exclude:
        if skill in text:
            reasons_not.append(f"Technologie exclue: {skill}")

    # ═══ ROLE FIT (0-100) ═══

    # Check if title matches target titles
    title_match_score = 0
    for target in titles_target:
        # Check word overlap
        target_words = set(target.split())
        title_words = set(title_lower.split())
        overlap = target_words & title_words
        if overlap:
            match_pct = len(overlap) / len(target_words) * 100
            title_match_score = max(title_match_score, int(match_pct))

    # Check current title match
    if current_title:
        current_words = set(current_title.split())
        title_words = set(title_lower.split())
        overlap = current_words & title_words
        if overlap:
            match_pct = len(overlap) / len(current_words) * 100
            title_match_score = max(title_match_score, int(match_pct * 0.8))

    dims["roleFit"] = min(100, title_match_score)
    if title_match_score >= 60:
        reasons_apply.append(f"Titre correspond: '{title}'")

    # ═══ SKILL FIT (0-100) ═══

    # Matched = user skills found in offer (offer wants them, user has them)
    # Missing = user core skills NOT in offer (offer doesn't need them — not a problem)
    # The score is: how many of MY skills does this offer want?
    for skill in skills_core:
        if skill in text:
            matched_skills.append(skill)
    for skill in skills_secondary:
        if skill in text:
            matched_skills.append(skill)

    # Skill fit = how many matches out of all user skills
    # BUT: if the offer mentions few skills, a small match still counts
    all_user_skills = skills_core + skills_secondary
    if matched_skills:
        # At least some skills match — score based on count
        if len(matched_skills) >= 4:
            dims["skillFit"] = 100
        elif len(matched_skills) >= 3:
            dims["skillFit"] = 85
        elif len(matched_skills) >= 2:
            dims["skillFit"] = 65
        elif len(matched_skills) >= 1:
            dims["skillFit"] = 45
    else:
        dims["skillFit"] = 10
        missing_skills = skills_core[:3]  # show what the user has that offer doesn't mention

    # Check for excluded skills in the offer
    excluded_found = [s for s in skills_exclude if s in text]
    if excluded_found:
        dims["skillFit"] = max(0, dims["skillFit"] - 40)
        reasons_not.append(f"Techno exclue trouvee: {', '.join(excluded_found)}")

    if len(matched_skills) >= 2:
        reasons_apply.append(f"{len(matched_skills)} competences matchent: {', '.join(matched_skills[:4])}")
    if not matched_skills and all_user_skills:
        reasons_not.append(f"Aucune competence ne matche")

    # ═══ EXPERIENCE FIT (0-100) ═══

    exp_years = extract_experience_years(text)
    offer_exp_min = min(exp_years) if exp_years else (offer.get("experience_min", 0) or 0)
    offer_exp_max = max(exp_years) if exp_years else offer_exp_min

    if offer_exp_min == 0:
        dims["experienceFit"] = 100
        reasons_apply.append("Debutant accepte")
    elif offer_exp_min <= 1:
        dims["experienceFit"] = 90
    elif offer_exp_min <= exp_max:
        dims["experienceFit"] = max(30, 80 - (offer_exp_min - 1) * 15)
    else:
        dims["experienceFit"] = max(0, 30 - (offer_exp_min - exp_max) * 15)
        reasons_not.append(f"Demande {offer_exp_min}+ ans (votre max: {exp_max})")

    # Hard block if WAY over
    if offer_exp_min > exp_max + 2:
        return _make_result(REJECT, 0, dims, matched_skills, missing_skills,
                           reasons_apply, [f"Experience requise: {offer_exp_min} ans (votre max: {exp_max})"])

    # ═══ SENIORITY RISK (0=safe, 100=very risky) ═══

    seniority_score = 0
    if seniority_block:
        if _TITLE_SENIORITY.search(title):
            seniority_score += 60
            reasons_not.append(f"Titre senior/lead detecte")
        seniority_hits = sum(1 for w in _SENIORITY_WORDS if w in text)
        seniority_score += seniority_hits * 20
        if seniority_hits:
            reasons_not.append(f"{seniority_hits} signal(s) de seniorite dans la description")

    dims["seniorityRisk"] = min(100, seniority_score)

    # Hard block if very senior
    if seniority_block and seniority_score >= 80:
        return _make_result(REJECT, 0, dims, matched_skills, missing_skills,
                           reasons_apply, reasons_not + ["Poste trop senior"])

    # Junior signals boost
    junior_in_title = any(s in title_lower for s in _JUNIOR_SIGNALS)
    junior_in_desc = sum(1 for s in _JUNIOR_SIGNALS if s in text)
    if junior_in_title:
        dims["experienceFit"] = 100
        dims["seniorityRisk"] = 0
        reasons_apply.append("Poste junior")

    # ═══ LOCATION FIT (0-100) ═══

    loc_lower = location.lower()
    if not cities:
        dims["locationFit"] = 50  # no preference = neutral
    else:
        city_match = any(c in loc_lower for c in cities)
        # Also check IDF suburbs for Paris
        if "paris" in cities:
            idf = ["ile-de-france", "île-de-france", "la defense", "boulogne", "issy",
                   "nanterre", "saint-denis", "levallois", "courbevoie", "puteaux", "montreuil", "massy"]
            if any(s in loc_lower for s in idf):
                city_match = True
        if city_match:
            dims["locationFit"] = 100
            reasons_apply.append(f"Localisation: {location}")
        else:
            dims["locationFit"] = 0
            reasons_not.append(f"Localisation: {location} (pas dans vos villes)")

    # Hard block if location doesn't match at all
    if cities and dims["locationFit"] == 0 and location:
        return _make_result(REJECT, 0, dims, matched_skills, missing_skills,
                           reasons_apply, reasons_not)

    # ═══ CONTRACT FIT (0-100) ═══

    offer_contract = contract.lower()
    if not contracts:
        dims["contractFit"] = 50
    elif not offer_contract:
        dims["contractFit"] = 70  # unknown contract = probably OK
    elif offer_contract in contracts or any(c in offer_contract for c in contracts):
        dims["contractFit"] = 100
    elif "freelance" in contracts and offer_contract in ("independant", "mission", "interim"):
        dims["contractFit"] = 100
    else:
        dims["contractFit"] = 20
        reasons_not.append(f"Contrat: {contract} (recherche: {', '.join(contracts)})")

    # ═══ COMPUTE FINAL SCORE & RECOMMENDATION ═══

    # Weighted average
    weights = {
        "roleFit": 25,
        "skillFit": 30,
        "experienceFit": 20,
        "seniorityRisk": -15,  # negative = penalty
        "locationFit": 5,
        "contractFit": 5,
    }
    total_weight = sum(abs(w) for w in weights.values())
    weighted_score = sum(dims[k] * weights[k] for k in weights) / total_weight
    final_score = max(0, min(100, int(weighted_score)))

    # Determine recommendation
    # Junior + title match = always STRONG_APPLY
    if junior_in_title and dims["roleFit"] >= 40 and dims["skillFit"] >= 40:
        recommendation = STRONG_APPLY
        final_score = max(final_score, 90)
    elif final_score >= 70 and dims["experienceFit"] >= 80:
        recommendation = STRONG_APPLY
    elif final_score >= 50 and dims["experienceFit"] >= 50:
        recommendation = APPLY
    elif final_score >= 30:
        recommendation = STRETCH
    elif final_score >= 10:
        recommendation = LOW_PRIORITY
    else:
        recommendation = REJECT

    return _make_result(recommendation, final_score, dims, matched_skills, missing_skills,
                       reasons_apply, reasons_not)


def _make_result(recommendation, score, dims, matched, missing, why_apply, why_not):
    return {
        "recommendation": recommendation,
        "score": score,
        "dimensions": dims,
        "matchedSkills": matched,
        "missingSkills": missing[:5],
        "reasoning": {
            "whyApply": why_apply[:3],
            "whyNotApply": why_not[:3],
        },
    }
