#!/usr/bin/env python3
"""
Job Apply Tool — Pipeline principal
Usage: python main.py
"""

import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from src.adapter import analyze_offer, select_and_adapt_bullets, generate_cover_letter, load_truth
from src.compiler import compile_cv, compile_letter
from src.tracker import add_application


def slugify(text):
    return text.lower().replace(" ", "_").replace("'", "").replace("/", "-")[:30]


def run_pipeline(offer_text, apply_link=""):
    truth = load_truth()

    # 1. Analyse de l'offre
    print("[1/5] Analyse de l'offre...")
    analysis = analyze_offer(offer_text)
    print(f"      Track: {analysis['track']} | Tone: {analysis['tone']} | Seniority: {analysis['seniority']}")
    print(f"      Keywords: {', '.join(analysis['keywords'][:8])}")
    print(f"      Titre suggéré: {analysis['title_suggestion']}")

    # 2. Sélection et adaptation des bullets
    print("[2/5] Adaptation du CV...")
    adapted = select_and_adapt_bullets(analysis, truth)

    # 3. Génération de la lettre
    print("[3/5] Génération de la lettre de motivation...")
    letter = generate_cover_letter(offer_text, analysis, truth)

    # 4. Compilation PDF
    company = analysis.get("title_suggestion", "unknown").split()[-1]
    # Essayer d'extraire le nom de l'entreprise du texte
    date_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join("output", f"{slugify(analysis.get('company_type', 'company'))}_{slugify(analysis['title_suggestion'])}_{date_str}")

    print(f"[4/5] Compilation PDF → {output_dir}")
    cv_path = compile_cv(truth, analysis, adapted, output_dir)
    letter_path = compile_letter(letter, truth, output_dir)

    # Save summary
    summary = {
        "analysis": analysis,
        "adapted_bullets": adapted,
        "letter": letter,
        "cv_path": cv_path,
        "letter_path": letter_path,
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    # 5. Tracking
    print("[5/5] Enregistrement dans le tracker...")
    add_application(
        company=analysis.get("company_type", "Unknown"),
        role=analysis["title_suggestion"],
        track=analysis["track"],
        output_dir=output_dir,
        apply_link=apply_link,
    )

    print(f"\nTerminé ! Fichiers dans : {output_dir}/")
    print(f"  CV:     {cv_path}")
    print(f"  Lettre: {letter_path}")
    return output_dir


def main():
    print("=" * 60)
    print("  JOB APPLY TOOL — Omar Ajraoui")
    print("=" * 60)
    print("\nColle le texte de l'offre (termine par une ligne vide + ENTER):\n")

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "" and lines:
            break
        lines.append(line)

    offer_text = "\n".join(lines)
    if not offer_text.strip():
        print("Aucune offre fournie.")
        sys.exit(1)

    apply_link = input("\nLien pour postuler (optionnel, ENTER pour skip): ").strip()

    run_pipeline(offer_text, apply_link)


if __name__ == "__main__":
    main()
