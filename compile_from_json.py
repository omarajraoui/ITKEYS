#!/usr/bin/env python3
"""
Compile CV + lettre depuis data/latest_inspo.json (généré par Claude).
Usage: python compile_from_json.py
"""

import json
import os
import sys
from datetime import datetime

# Ensure pdflatex is in PATH
os.environ["PATH"] = "/usr/local/texlive/2026basic/bin/universal-darwin:" + os.environ.get("PATH", "")

from src.compiler import compile_cv, compile_letter
from src.adapter import load_truth
from src.tracker import add_application


def slugify(text):
    return text.lower().replace(" ", "_").replace("'", "").replace("/", "-")[:30]


def main():
    inspo_path = os.path.join("data", "latest_inspo.json")
    if not os.path.exists(inspo_path):
        print("Erreur: data/latest_inspo.json introuvable. Demande à Claude de le générer.")
        sys.exit(1)

    with open(inspo_path, "r") as f:
        inspo = json.load(f)

    truth = load_truth()
    analysis = inspo["analysis"]
    adapted = inspo["adapted_bullets"]
    letter = inspo["letter"]

    company = slugify(analysis.get("company_name", "company"))
    title = slugify(analysis["title_suggestion"])
    date_str = datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join("output", f"{company}_{title}_{date_str}")

    print(f"[1/3] Compilation CV → {output_dir}")
    cv_path = compile_cv(truth, analysis, adapted, output_dir)

    print(f"[2/3] Compilation lettre → {output_dir}")
    letter_path = compile_letter(letter, truth, output_dir, offer_analysis=analysis)

    # Save full summary
    summary = {
        "analysis": analysis,
        "adapted_bullets": adapted,
        "letter": letter,
        "cv_path": cv_path,
        "letter_path": letter_path,
    }
    with open(os.path.join(output_dir, "summary.json"), "w") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[3/3] Tracking...")
    add_application(
        company=analysis.get("company_name", "Unknown"),
        role=analysis["title_suggestion"],
        track=analysis["track"],
        output_dir=output_dir,
        apply_link=analysis.get("apply_link", ""),
    )

    print(f"\nTerminé ! Fichiers dans : {output_dir}/")
    print(f"  CV:     {cv_path}")
    print(f"  Lettre: {letter_path}")


if __name__ == "__main__":
    main()
