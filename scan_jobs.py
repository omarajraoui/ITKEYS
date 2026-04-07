#!/usr/bin/env python3
"""
Scan les offres IT sur WTTJ + France Travail.
Score et filtre par pertinence pour le profil Omar.
Usage: python scan_jobs.py
"""

import json
import os
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from src.scraper import search_all


TECHNICIEN_PREFS = {
    "current_title": "Technicien informatique",
    "titles_target": [
        "technicien support informatique",
        "technicien helpdesk",
        "technicien systemes et reseaux",
        "technicien deploiement",
        "technicien N1 N2",
        "technicien N2 N3",
        "technicien maintenance informatique",
        "technicien informatique",
        "technicien poste de travail",
        "technicien infrastructure",
        "gestionnaire parc informatique",
    ],
    "skills_core": ["helpdesk", "Active Directory", "GLPI", "ticketing", "Office 365"],
    "skills_secondary": ["VMware", "SCCM", "Windows Server", "ITIL"],
    "skills_exclude": [],
    "keywords_exclude": [
        "chef de projet", "lead", "architecte", "consultant senior",
        "manager", "directeur", "responsable", "expert",
        "developpeur", "data engineer", "data scientist",
        "commercial", "marketing", "comptable",
    ],
    "experience_max": 2,
    "seniority_block": True,
    "cities": ["Paris"],
    "contracts": ["CDI", "CDD"],
}


def main():
    import os
    scan_mode = os.environ.get("SCAN_MODE", "")

    # Technicien mode: use hardcoded technicien prefs
    if scan_mode == "technicien":
        print("[MODE] Technicien/Support scan")
        user_prefs = TECHNICIEN_PREFS
    else:
        # Check if user_prefs passed via env var (from server.py)
        prefs_path = os.environ.get("USER_PREFS_PATH")
        user_prefs = None
        if prefs_path and os.path.exists(prefs_path):
            try:
                with open(prefs_path) as f:
                    user_prefs = json.load(f)
                print(f"[user] Loaded preferences from {prefs_path}")
            except Exception:
                pass

    offers = search_all(max_pages=2, enrich=True, user_prefs=user_prefs)

    if not offers:
        print("\nAucune offre pertinente trouvée.")
        return

    # Determine output path (per-user or global)
    output_path = os.environ.get("SCAN_OUTPUT_PATH", "data/scan_results.json")

    # Assign unique IDs (preserve existing IDs if re-scanning)
    existing_ids = set()
    existing_path = output_path
    if os.path.exists(existing_path):
        try:
            with open(existing_path) as f:
                old = json.load(f)
            for o in old.get("offers", []):
                if o.get("id"):
                    existing_ids.add(o["id"])
        except Exception:
            pass

    next_id = max((int(i) for i in existing_ids if str(i).isdigit()), default=0) + 1
    # Build URL→ID map from existing
    url_to_id = {}
    if os.path.exists(existing_path):
        try:
            with open(existing_path) as f:
                old = json.load(f)
            for o in old.get("offers", []):
                if o.get("id") and o.get("url"):
                    url_to_id[o["url"]] = o["id"]
        except Exception:
            pass

    for o in offers:
        if o.get("url") and o["url"] in url_to_id:
            o["id"] = url_to_id[o["url"]]
        else:
            o["id"] = next_id
            next_id += 1

    # Sauvegarder
    output = {
        "scan_date": datetime.now().isoformat(),
        "total": len(offers),
        "offers": offers,
    }
    os.makedirs(os.path.dirname(output_path) or "data", exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    # Affichage
    print(f"\n{'─' * 100}")
    print(f"{'#':>3} {'Sc':>3} {'Age':>4} {'Loc':>3} {'Contrat':<5} {'Titre':<38} {'Entreprise':<20} {'Lieu'}")
    print(f"{'─' * 100}")

    for i, o in enumerate(offers[:50], 1):
        days = o.get("days_ago", 99)
        days_str = f"{days}j" if days < 99 else "?"
        score = o.get("score", 0)
        contract = o.get("contract", "")[:4]
        title = o.get("title", "?")[:36]
        company = o.get("company", "")[:18]
        location = o.get("location", "")[:15]
        tier = o.get("location_tier", "T3")

        marker = "★" if score >= 40 else "●" if score >= 20 else "○"

        print(f"{i:>3} {marker}{score:>3} {days_str:>4} {tier:>3} {contract:<5} {title:<38} {company:<20} {location}")

    print(f"{'─' * 100}")
    print(f"\n★ 40+ = top match  ● 20+ = bon match  ○ = possible")
    print(f"T1 = Paris/Lyon/Sud  T2 = Grandes villes  T3 = Autres")
    print(f"\nRésultats : data/scan_results.json")
    print(f"→ Passe le numéro d'une offre à Claude pour générer CV + lettre + fiche prep.")


if __name__ == "__main__":
    main()
