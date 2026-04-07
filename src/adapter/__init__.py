import json
import os
from anthropic import Anthropic

client = Anthropic()

TRUTH_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "truth.json")


def load_truth():
    with open(TRUTH_PATH, "r") as f:
        return json.load(f)


def analyze_offer(offer_text):
    """Analyse l'offre -> detecte track, keywords, seniority, tone."""
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": f"""Analyse cette offre d'emploi et retourne un JSON avec :
- "track": "tech" ou "consulting"
- "keywords": liste des competences/technologies cles demandees
- "seniority": "junior", "mid", "senior"
- "tone": "startup", "esn", "grand_groupe", "cabinet_conseil"
- "title_suggestion": titre adapte pour le CV (en francais)
- "company_type": description courte du type d'entreprise

Offre :
{offer_text}

Reponds UNIQUEMENT avec le JSON, sans markdown.""",
            }
        ],
    )
    return json.loads(resp.content[0].text)


def select_and_adapt_bullets(offer_analysis, truth):
    """Selectionne et reecrit les bullets du pool pour matcher l'offre."""
    track = offer_analysis["track"]
    keywords = ", ".join(offer_analysis["keywords"])

    experiences_info = []
    for exp in truth["experiences"]:
        experiences_info.append(
            {
                "id": exp["id"],
                "company": exp["company"],
                "title": exp["titles"][track],
                "bullets_pool": exp["bullets_pool"][track],
                "stack": exp["stack"],
            }
        )

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f"""Tu adaptes un CV pour une offre.
Track : {track}
Keywords de l'offre : {keywords}
Seniority : {offer_analysis['seniority']}
Tone : {offer_analysis['tone']}

Voici les experiences avec leur pool de bullets :
{json.dumps(experiences_info, ensure_ascii=False, indent=2)}

Pour CHAQUE experience, selectionne 3-5 bullets les plus pertinents du pool et reecris-les pour :
1. Integrer naturellement les keywords de l'offre quand c'est honnete
2. Adapter le ton (startup = impact/ownership, grand_groupe = process/scale, conseil = cadrage/pilotage)
3. Garder la verite — ne jamais inventer

Retourne un JSON :
{{
  "experiences": [
    {{
      "id": "freelance",
      "bullets": ["bullet reecrit 1", "bullet reecrit 2", ...]
    }},
    ...
  ]
}}

Reponds UNIQUEMENT avec le JSON, sans markdown.""",
            }
        ],
    )
    return json.loads(resp.content[0].text)


def generate_cover_letter(offer_text, offer_analysis, truth):
    """Genere une lettre de motivation adaptee."""
    track = offer_analysis["track"]
    summary = truth["summaries"][track]

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        messages=[
            {
                "role": "user",
                "content": f"""Ecris une lettre de motivation pour Omar Ajraoui.

Profil : {summary}
Formation : Master 2 MIAGE Paris Dauphine-PSL + Diplome Ingenieur ENSIAS
Track : {track}
Tone entreprise : {offer_analysis['tone']}

Offre :
{offer_text}

Regles :
- 3 paragraphes max : accroche, valeur ajoutee, motivation/closing
- Ton adapte ({offer_analysis['tone']}) : startup = direct/ownership, grand_groupe = structure, conseil = cadrage strategique
- Pas de "je me permets de", pas de formules creuses
- Mentionne 2-3 realisations concretes qui matchent l'offre
- Court : max 250 mots
- En francais

Retourne un JSON :
{{
  "subject": "Objet de la lettre",
  "body": "Texte complet de la lettre"
}}

Reponds UNIQUEMENT avec le JSON, sans markdown.""",
            }
        ],
    )
    return json.loads(resp.content[0].text)
