import json
import os
import subprocess

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "templates")


def _escape_latex(text):
    """Echappe les caracteres speciaux LaTeX."""
    chars = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for k, v in chars.items():
        text = text.replace(k, v)
    return text


def _build_experiences_latex(adapted_bullets, track, truth):
    """Construit le bloc LaTeX des experiences."""
    latex = ""
    bullet_map = {e["id"]: e["bullets"] for e in adapted_bullets["experiences"]}

    for exp in truth["experiences"]:
        title = exp["titles"][track]
        bullets = bullet_map.get(exp["id"], exp["bullets_pool"][track][:4])

        latex += f"""\\resumeSubheading
{{{_escape_latex(exp['company'])}}}{{{exp['date_start']} -- {exp['date_end']}}}
{{{_escape_latex(title)}}}{{{exp['location']}}}

\\resumeItemListStart
"""
        for b in bullets:
            latex += f"\\resumeItem{{{_escape_latex(b)}}}\n"

        latex += "\\resumeItemListEnd\n\n"
        latex += f"\\textit{{\\small \\textbf{{Stack :}} {', '.join(exp['stack'][:10])}.}}\n\n"
        latex += "\\vspace{5pt}\n\n"

    return latex


def _build_education_latex(truth, track):
    """Construit le bloc LaTeX de la formation."""
    latex = ""
    for edu in truth["education"]:
        latex += f"""\\resumeSubheading
{{{_escape_latex(edu['school'])}}}{{{edu['date_start']} -- {edu['date_end']}}}
{{{_escape_latex(edu['degree'])}}}{{{edu['location']}}}
"""
        if edu.get("memoir") and edu["memoir"].get(track):
            latex += f"""\\vspace{{3pt}}
\\begin{{itemize}}[leftmargin=0.2in,label={{}}]
\\item\\small{{\\textbf{{M\\'emoire :}} {_escape_latex(edu['memoir'][track])}}}
\\end{{itemize}}\\vspace{{-8pt}}
"""
        latex += "\\vspace{8pt}\n"
    return latex


def _build_skills_latex(truth, track):
    """Construit le bloc LaTeX des competences."""
    latex = ""
    for category, skills in truth["skills"][track].items():
        latex += f"\\textbf{{{_escape_latex(category)}}} : {_escape_latex(skills)} \\\\\n"
    return latex


def _build_languages_latex(truth):
    """Construit le bloc LaTeX des langues."""
    parts = []
    for lang in truth["profile"]["languages"]:
        parts.append(f"\\textbf{{{lang['lang']}}} ({lang['level']})")
    return " $|$ ".join(parts)


def _resolve_location(truth, offer_analysis):
    """Choisit l'adresse et la localisation en fonction de la ville de l'offre."""
    company_address = offer_analysis.get("company_address", "")
    offer_location = offer_analysis.get("offer_location", company_address).lower()

    locations = truth["profile"].get("locations", {})
    addresses = truth["profile"].get("addresses", {})

    offer_location = offer_location.replace("-", " ")

    # Chercher la ville qui matche
    # Mapping ville → clé d'adresse
    city_to_address_key = {
        "paris": "paris", "lyon": "lyon", "marseille": "marseille", "lille": "lille",
        "toulouse": "paris", "bordeaux": "paris", "nantes": "paris",
        "nice": "marseille", "sophia antipolis": "marseille", "antibes": "marseille",
        "aix en provence": "marseille", "cannes": "marseille", "toulon": "marseille",
        "montpellier": "marseille",
    }
    default_addr = truth.get("profile", {}).get("address", "Paris, France")
    default_loc = truth.get("profile", {}).get("location", "Paris, France")
    for city_key, addr_key in city_to_address_key.items():
        if city_key in offer_location:
            return (
                addresses.get(addr_key, addresses.get("paris", default_addr)),
                locations.get(city_key, locations.get(addr_key, locations.get("default", default_loc))),
            )

    # Ile-de-France par défaut
    idf_keywords = ["rueil", "courbevoie", "nanterre", "issy", "boulogne", "saint-denis",
                     "fontenay", "montreuil", "la défense", "la defense", "puteaux",
                     "levallois", "clichy", "massy", "villejuif", "ivry", "plessis"]
    for kw in idf_keywords:
        if kw in offer_location:
            return addresses.get("paris"), locations.get("paris", "Paris, France")

    # Défaut : Paris
    return addresses.get("paris", default_addr), locations.get("default", default_loc)


def _slugify_company(name):
    """Slugifie le nom d'entreprise pour le nom de fichier."""
    import unicodedata
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().replace(" ", "").replace("'", "").replace("-", "")
    name = ''.join(c for c in name if c.isalnum())
    return name[:30]


def compile_cv(truth, offer_analysis, adapted_bullets, output_dir, templates_dir=None):
    """Compile le CV en PDF."""
    track = offer_analysis["track"]

    tpl_dir = templates_dir or TEMPLATES_DIR
    template_path = os.path.join(tpl_dir, "cv_master.tex")
    with open(template_path, "r") as f:
        template = f.read()

    address, location = _resolve_location(truth, offer_analysis)

    profile = truth.get("profile", {})
    summaries = truth.get("summaries", {})
    replacements = {
        "<<name>>": profile.get("name", ""),
        "<<title>>": _escape_latex(offer_analysis.get("title_suggestion", "")),
        "<<phone>>": profile.get("phone", ""),
        "<<email>>": profile.get("email", ""),
        "<<linkedin>>": profile.get("linkedin", ""),
        "<<linkedin_short>>": profile.get("linkedin", ""),
        "<<github>>": profile.get("github", ""),
        "<<location>>": location,
        "<<summary>>": _escape_latex(offer_analysis.get("adapted_summary") or summaries.get(track, "")),
        "<<experiences>>": _build_experiences_latex(adapted_bullets, track, truth),
        "<<education>>": _build_education_latex(truth, track),
        "<<skills>>": _build_skills_latex(truth, track),
        "<<languages>>": _build_languages_latex(truth),
    }

    tex_content = template
    for placeholder, value in replacements.items():
        tex_content = tex_content.replace(placeholder, value)

    os.makedirs(output_dir, exist_ok=True)
    company_slug = _slugify_company(offer_analysis.get("company_name", "company"))
    name_slug = _slugify_company(truth["profile"].get("name", "candidat"))
    title_slug = _slugify_company(offer_analysis.get("title_suggestion", "cv"))
    base_name = f"{name_slug}_{title_slug}_{company_slug}"

    tex_path = os.path.join(output_dir, f"{base_name}.tex")
    with open(tex_path, "w") as f:
        f.write(tex_content)

    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_path],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"pdflatex warning/error (last 500 chars):\n{result.stdout[-500:].decode('utf-8', errors='replace')}")

    # Run twice for references
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_path],
        capture_output=True,
    )

    return os.path.join(output_dir, f"{base_name}.pdf")


def compile_letter(letter_data, truth, output_dir, offer_analysis=None, templates_dir=None):
    """Compile la lettre de motivation en PDF."""
    os.makedirs(output_dir, exist_ok=True)

    profile = truth.get('profile', {})
    name = profile.get('name', '') or 'Candidat'
    name_parts = name.split()
    first_name = name_parts[0] if name_parts else ''
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ''
    linkedin_raw = profile.get('linkedin', '') or ''
    linkedin_short = linkedin_raw.replace('linkedin.com/in/', '').replace('https://', '').replace('http://', '')

    # Résoudre l'adresse en fonction de la localisation de l'offre
    if offer_analysis:
        address, _ = _resolve_location(truth, offer_analysis)
    else:
        # Fallback: deviner depuis company_address dans letter_data
        fake_analysis = {"company_address": letter_data.get("company_address", "")}
        address, _ = _resolve_location(truth, fake_analysis)

    tpl_dir = templates_dir or TEMPLATES_DIR
    template_path = os.path.join(tpl_dir, "letter_master.tex")
    with open(template_path, "r") as f:
        template = f.read()

    company_name = letter_data.get("company_name", "")
    company_address = letter_data.get("company_address", "")
    position = letter_data.get("position", letter_data.get("subject", ""))

    # Sanitize body: replace any remaining [Entreprise] / [Poste] placeholders
    import re as _re
    body = letter_data.get("body", "")
    if company_name:
        body = _re.sub(
            r'\[(?:Entreprise|Nom de l\'entreprise|Société|Company|entreprise|société)\]',
            company_name, body, flags=_re.IGNORECASE,
        )
    if position:
        body = _re.sub(
            r'\[(?:Poste|Position|Titre|titre du poste|poste)\]',
            position, body, flags=_re.IGNORECASE,
        )

    replacements = {
        "<<name>>": profile.get("name", ""),
        "<<first_name>>": first_name or "",
        "<<last_name>>": last_name or "",
        "<<phone>>": profile.get("phone", "") or "",
        "<<address>>": address or "",
        "<<email>>": profile.get("email", "") or "",
        "<<linkedin>>": profile.get("linkedin", "") or "",
        "<<linkedin_short>>": linkedin_short or "",
        "<<company_name>>": _escape_latex(company_name or ""),
        "<<company_address>>": _escape_latex(company_address or ""),
        "<<position>>": _escape_latex(position or ""),
        "<<body>>": _escape_latex(body or ""),
    }

    tex_content = template
    for placeholder, value in replacements.items():
        tex_content = tex_content.replace(placeholder, value or "")

    company_slug = _slugify_company(letter_data.get("company_name", "company"))
    name_slug = _slugify_company(truth.get("profile", {}).get("name", "candidat"))
    title_slug = _slugify_company(letter_data.get("position", "lettre"))
    base_name = f"{name_slug}_{title_slug}_{company_slug}"

    tex_path = os.path.join(output_dir, f"{base_name}.tex")
    with open(tex_path, "w") as f:
        f.write(tex_content)

    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-output-directory", output_dir, tex_path],
        capture_output=True,
    )
    if result.returncode != 0:
        print(f"pdflatex letter warning (last 500 chars):\n{result.stdout[-500:].decode('utf-8', errors='replace')}")

    return os.path.join(output_dir, f"{base_name}.pdf")
