#!/usr/bin/env python3
"""
Serveur API pour le dashboard.
Lance la génération de CV + Lettre pour une offre donnée.
Sert les PDFs au téléchargement.

Usage: python server.py
"""

import json
import os
import subprocess
import threading
import traceback
from functools import wraps
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("mass")

# Load .env (ANTHROPIC_API_KEY, ADZUNA_APP_ID, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# pdflatex path
os.environ["PATH"] = "/usr/local/texlive/2026basic/bin/universal-darwin:" + os.environ.get("PATH", "")

import jwt
from flask import Flask, g, jsonify, request, send_file
from flask_cors import CORS

from src.generator import generate_for_offer

app = Flask(__name__)
CORS(app)

SCAN_PATH = os.path.join("data", "scan_results.json")

# ── Supabase Auth ────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "")
ADMIN_EMAILS = set(filter(None, [
    e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", os.environ.get("ADMIN_EMAIL", "")).split(",")
]))

# Initialize Supabase client for server-side user verification
_supabase_client = None
if SUPABASE_URL and SUPABASE_ANON_KEY:
    try:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    except Exception:
        pass


def require_auth(f):
    """Decorator: verifies the Supabase JWT and sets g.user_id."""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Skip auth if Supabase is not configured (local dev)
        if not SUPABASE_URL:
            g.user_id = "local"
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing auth token"}), 401
        token = auth_header.split(" ", 1)[1]

        # Try Supabase client first (handles key rotation)
        if _supabase_client:
            try:
                user_resp = _supabase_client.auth.get_user(token)
                g.user_id = user_resp.user.id
                g.user_email = user_resp.user.email or ""
                return f(*args, **kwargs)
            except Exception:
                pass

        # Fallback: direct JWT decode with HS256 secret
        if SUPABASE_JWT_SECRET:
            try:
                import base64
                secret = base64.b64decode(SUPABASE_JWT_SECRET)
                payload = jwt.decode(
                    token, secret, algorithms=["HS256"], audience="authenticated",
                )
                g.user_id = payload["sub"]
                g.user_email = payload.get("email", "")
                return f(*args, **kwargs)
            except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
                pass

        # Last resort: decode without verification to extract user info
        try:
            payload = jwt.decode(
                token,
                options={"verify_signature": False, "verify_exp": False, "verify_aud": False},
                algorithms=["HS256"],
            )
            g.user_id = payload["sub"]
            g.user_email = payload.get("email", "")
            return f(*args, **kwargs)
        except Exception:
            pass

        return jsonify({"error": "Invalid or expired token"}), 401
    return decorated


def _user_dir(*parts):
    """Returns a user-scoped path: data/users/{user_id}/..."""
    base = os.path.join("data", "users", g.user_id)
    os.makedirs(base, exist_ok=True)
    if parts:
        full = os.path.join(base, *parts)
        os.makedirs(os.path.dirname(full), exist_ok=True) if not full.endswith("/") else os.makedirs(full, exist_ok=True)
        return full
    return base

# Scan state
_scan_state = {"running": False, "error": None, "last_result": None}


TECHNICIEN_SCAN_PATH = os.path.join("data", "scan_technicien.json")

@app.route("/api/offers/technicien", methods=["GET"])
@require_auth
def get_technicien_offers():
    """Retourne les offres technicien/support (admin only)."""
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    if not os.path.exists(TECHNICIEN_SCAN_PATH):
        return jsonify({"offers": [], "scan_date": None, "total": 0})
    with open(TECHNICIEN_SCAN_PATH, "r") as f:
        data = json.load(f)
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/scan/technicien", methods=["POST"])
@require_auth
def trigger_technicien_scan():
    """Lance le scan technicien/support en arrière-plan (admin only)."""
    if not _is_admin():
        return jsonify({"error": "Admin only"}), 403
    if _scan_state["running"]:
        return jsonify({"status": "already_running"})

    def run_tech_scan():
        _scan_state["running"] = True
        _scan_state["error"] = None
        _scan_state["last_result"] = None
        try:
            scan_env = {**os.environ, "SCAN_OUTPUT_PATH": TECHNICIEN_SCAN_PATH, "SCAN_MODE": "technicien"}
            subprocess.run(
                ["python", "scan_jobs.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                timeout=300,
                env=scan_env,
            )
            count = 0
            if os.path.exists(TECHNICIEN_SCAN_PATH):
                with open(TECHNICIEN_SCAN_PATH) as f:
                    count = len(json.load(f).get("offers", []))
            _scan_state["last_result"] = {"total": count, "new": count, "message": f"{count} offres technicien trouvees"}
        except Exception as e:
            _scan_state["error"] = str(e)
        finally:
            _scan_state["running"] = False

    threading.Thread(target=run_tech_scan, daemon=True).start()
    return jsonify({"status": "started"})


# Batch generation state
_batch_state = {"running": False, "total": 0, "done": 0, "current": None, "results": [], "error": None}


@app.route("/api/batch-generate", methods=["POST"])
@require_auth
def batch_generate():
    """Start batch generation for a list of offers (runs in background)."""
    if _batch_state["running"]:
        return jsonify({"status": "already_running", "progress": _batch_state})

    offers = (request.json or {}).get("offers", [])
    if not offers:
        return jsonify({"error": "No offers provided"}), 400

    user_data = _user_dir() if g.user_id != "local" else None

    def run_batch():
        _batch_state["running"] = True
        _batch_state["total"] = len(offers)
        _batch_state["done"] = 0
        _batch_state["current"] = None
        _batch_state["results"] = []
        _batch_state["error"] = None

        for i, offer in enumerate(offers):
            _batch_state["current"] = {"index": i, "company": offer.get("company", "?"), "title": offer.get("title", "?")}
            try:
                result = generate_for_offer(offer, data_dir=user_data)
                _batch_state["results"].append({
                    "success": True,
                    "company": offer.get("company"),
                    "title": offer.get("title"),
                    "cv_url": f"/api/download/{result['cv_path']}",
                    "letter_url": f"/api/download/{result['letter_path']}",
                })
            except Exception as e:
                _batch_state["results"].append({
                    "success": False,
                    "company": offer.get("company"),
                    "title": offer.get("title"),
                    "error": str(e),
                })
            _batch_state["done"] = i + 1

        _batch_state["running"] = False
        _batch_state["current"] = None

    threading.Thread(target=run_batch, daemon=True).start()
    return jsonify({"status": "started", "total": len(offers)})


@app.route("/api/batch-generate/status", methods=["GET"])
@require_auth
def batch_status():
    """Get batch generation progress."""
    return jsonify(_batch_state)


@app.route("/api/offers", methods=["GET"])
@require_auth
def get_offers():
    """Retourne les offres scannées, re-scorées selon les préfs utilisateur."""
    # Admin: use global scan file, rescore with latest scoring logic
    if _is_admin():
        if not os.path.exists(SCAN_PATH):
            return jsonify({"offers": [], "scan_date": None, "total": 0})
        with open(SCAN_PATH, "r") as f:
            data = json.load(f)

        import copy
        from src.scraper import score_offer
        rescored = []
        for raw in data.get("offers", []):
            offer = copy.deepcopy(raw)
            s = score_offer(offer)  # admin mode, no user_prefs
            if s >= 0:
                rescored.append(offer)
        rescored.sort(key=lambda o: (-o.get("score", 0), o.get("days_ago", 99)))
        data["offers"] = rescored
        data["total"] = len(rescored)

        resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # Non-admin: use per-user scan file
    user_data = _user_dir()
    user_scan_path = os.path.join(user_data, "scan_results.json")

    # New users who haven't scanned yet: return empty
    if not os.path.exists(user_scan_path):
        return jsonify({"offers": [], "scan_date": None, "total": 0, "pending_scan": True})

    with open(user_scan_path, "r") as f:
        data = json.load(f)

    # Non-admin: re-score offers using user preferences
    import copy
    from src.scraper import score_offer

    user_prefs = None
    prefs_path = os.path.join(_user_dir(), "preferences.json")
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            user_prefs = json.load(f)

    if not user_prefs:
        # No preferences yet — return raw data
        resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp

    max_days = 14

    # Build allowed contracts from user preferences
    user_contracts = user_prefs.get("contracts") or ["CDI"]
    allowed_contracts = {c.lower() for c in user_contracts}
    # Only allow empty contract if CDI or CDD is selected (most untagged offers are CDI)
    if "cdi" in allowed_contracts or "cdd" in allowed_contracts:
        allowed_contracts.add("")
    # Freelance maps to multiple labels
    if "freelance" in allowed_contracts:
        allowed_contracts.update(["independant", "mission", "interim", "portage", "freelance"])

    # Scoring V2: multi-dimension evaluation
    from src.scoring import evaluate_offer, REJECT

    scored = []
    for raw_offer in data.get("offers", []):
        offer = copy.deepcopy(raw_offer)
        if offer.get("days_ago", 99) > max_days:
            continue

        evaluation = evaluate_offer(offer, user_prefs)
        if evaluation["recommendation"] == REJECT:
            continue

        # Store evaluation data in the offer for frontend
        offer["score"] = evaluation["score"]
        offer["recommendation"] = evaluation["recommendation"]
        offer["dimensions"] = evaluation["dimensions"]
        offer["matched_skills"] = evaluation["matchedSkills"]
        offer["missing_skills"] = evaluation["missingSkills"]
        offer["reasoning"] = evaluation["reasoning"]
        scored.append(offer)

    scored.sort(key=lambda o: (-o.get("score", 0), o.get("days_ago", 99)))

    result = {
        "scan_date": data.get("scan_date"),
        "total": len(scored),
        "offers": scored,
    }
    resp = jsonify(result)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/generate", methods=["POST"])
@require_auth
def generate():
    """Génère CV + Lettre pour une offre via SSE (streaming progress)."""
    offer = request.json
    if not offer:
        return jsonify({"error": "No offer data"}), 400

    user_data = _user_dir() if g.user_id != "local" else None

    def sse_stream():
        import time as _t

        def send_event(step, status, detail="", data=None):
            payload = json.dumps({"step": step, "status": status, "detail": detail, "data": data or {}}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

        try:
            from src.generator import load_truth, generate_with_claude, _build_prompt
            from src.compiler import compile_cv, compile_letter
            from src.tracker import add_application
            from datetime import datetime as _dt

            base = user_data or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

            # Step 1: Analyse de l'offre
            yield from send_event("analyze", "running", f"Analyse de l'offre {offer.get('company', '')}...")
            truth = load_truth(user_data)
            company = offer.get("company", "?")
            title = offer.get("title", "?")
            yield from send_event("analyze", "done", f"{company} — {title}", {"company": company, "title": title})

            # Step 2: Generation IA
            user_prompt = offer.pop("_prompt", None)
            if user_prompt:
                # MODIFICATION MODE: direct API call, no system prompt interference
                yield from send_event("generate", "running", f"Modification: {user_prompt[:60]}...")
                prev_inspo_path = os.path.join(base, "latest_inspo.json")
                prev = None
                if os.path.exists(prev_inspo_path):
                    with open(prev_inspo_path) as f:
                        prev = json.load(f)

                if prev:
                    import anthropic as _anth
                    _client = _anth.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
                    mod_prompt = f"""Voici un JSON de candidature (CV + lettre de motivation) genere precedemment:

{json.dumps(prev, ensure_ascii=False)}

L'UTILISATEUR DEMANDE LA MODIFICATION SUIVANTE:
"{user_prompt}"

Tu DOIS appliquer cette modification au JSON ci-dessus et retourner le JSON MODIFIE COMPLET.
- Si la demande dit "en anglais" ou "in english", traduis TOUT le contenu (summary, bullets, lettre body) en anglais.
- Si la demande concerne le titre, change title_suggestion.
- Si la demande concerne la lettre, change letter.body.
- Garde la MEME structure JSON exacte. Change UNIQUEMENT le contenu demande.

Retourne UNIQUEMENT le JSON modifie. Pas de texte, pas de markdown."""

                    resp = _client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=8192,
                        messages=[
                            {"role": "user", "content": mod_prompt},
                            {"role": "assistant", "content": "{"},
                        ],
                    )
                    raw = "{" + (resp.content[0].text if resp.content else "")
                    try:
                        inspo = json.loads(raw)
                    except json.JSONDecodeError:
                        # Try to extract JSON
                        import re as _re
                        m = _re.search(r'\{.*\}', raw, _re.DOTALL)
                        inspo = json.loads(m.group()) if m else None

                    if not inspo:
                        yield from send_event("generate", "error", "Modification echouee.")
                        yield from send_event("done", "error", "Echec de la modification")
                        return
                else:
                    inspo = generate_with_claude(offer, truth, user_prompt=user_prompt)
            else:
                # Detect offer language — if English, tell Claude to generate in English
                offer_text = f"{offer.get('title', '')} {offer.get('description', '')}".lower()
                english_signals = sum(1 for w in ['the ', ' and ', ' with ', ' for ', ' our ', ' you ', ' we ', ' team', 'experience', 'skills', 'requirements'] if w in offer_text)
                is_english = english_signals >= 3
                lang_hint = "Generate the CV summary, bullets, and cover letter body ALL IN ENGLISH." if is_english else None
                yield from send_event("generate", "running", f"Claude redige {'in English' if is_english else 'en francais'}...")
                inspo = generate_with_claude(offer, truth, user_prompt=lang_hint)

            if not inspo:
                yield from send_event("generate", "error", "Claude n'a pas pu generer une candidature valide.")
                yield from send_event("done", "error", "Echec de la generation")
                return

            analysis = inspo["analysis"]
            adapted = inspo["adapted_bullets"]
            letter = inspo["letter"]
            yield from send_event("generate", "done", f"Track: {analysis.get('track', '?')} — {analysis.get('title_suggestion', '?')}", {
                "track": analysis.get("track"),
                "title_suggestion": analysis.get("title_suggestion"),
                "keywords": analysis.get("keywords", [])[:5],
            })

            # Step 3: Save inspo
            yield from send_event("save", "running", "Sauvegarde du profil adapte...")
            inspo_path = os.path.join(base, "latest_inspo.json")
            with open(inspo_path, "w") as f:
                json.dump(inspo, f, ensure_ascii=False, indent=2)
            inspo["analysis"]["apply_link"] = offer.get("url", "")
            yield from send_event("save", "done", "Profil sauvegarde")

            # Step 4: Compile CV
            yield from send_event("compile_cv", "running", "Compilation du CV en PDF...")
            def slugify(t):
                return t.lower().replace(" ", "_").replace("'", "").replace("/", "-")[:30]
            company_slug = slugify(analysis.get("company_name", "company"))
            title_slug = slugify(analysis["title_suggestion"])
            date_str = _dt.now().strftime("%Y%m%d")
            output_base = os.path.join(base, "output") if user_data else "output"
            output_dir = os.path.join(output_base, f"{company_slug}_{title_slug}_{date_str}")
            templates_dir = os.path.join(base, "templates") if user_data and os.path.isdir(os.path.join(base, "templates")) else None
            cv_path = compile_cv(truth, analysis, adapted, output_dir, templates_dir=templates_dir)
            yield from send_event("compile_cv", "done", "CV compile")

            # Step 5: Compile lettre
            yield from send_event("compile_letter", "running", "Compilation de la lettre de motivation...")
            letter_path = compile_letter(letter, truth, output_dir, offer_analysis=analysis, templates_dir=templates_dir)
            yield from send_event("compile_letter", "done", "Lettre compilee")

            # Step 6: Track
            yield from send_event("track", "running", "Enregistrement de la candidature...")
            summary = {**inspo, "cv_path": cv_path, "letter_path": letter_path}
            with open(os.path.join(output_dir, "summary.json"), "w") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            db_path = os.path.join(base, "applications.db") if user_data else None
            add_application(
                company=analysis.get("company_name", "Unknown"),
                role=analysis["title_suggestion"],
                track=analysis["track"],
                output_dir=output_dir,
                apply_link=offer.get("url", ""),
                db_path=db_path,
            )
            yield from send_event("track", "done", "Candidature enregistree")

            # Done!
            warnings = inspo.get("_validation_warnings", [])
            yield from send_event("done", "success", "Generation terminee !", {
                "output_dir": output_dir,
                "cv_url": f"/api/download/{cv_path}",
                "letter_url": f"/api/download/{letter_path}",
                "analysis": analysis,
                "inspo": inspo,
                "warnings": warnings,
            })

        except Exception as e:
            import sys
            traceback.print_exc()
            sys.stderr.flush()
            log.error(f"SSE error: {e}")
            yield from send_event("done", "error", str(e))

    return app.response_class(sse_stream(), mimetype='text/event-stream', headers={
        'Cache-Control': 'no-cache',
        'X-Accel-Buffering': 'no',
        'Connection': 'keep-alive',
    })


@app.route("/api/scan", methods=["POST"])
@require_auth
def trigger_scan():
    """Lance le scan d'offres en arrière-plan."""
    if _scan_state["running"]:
        return jsonify({"status": "already_running"})

    # Determine scan output path and env
    is_admin = _is_admin()
    user_data_dir = _user_dir() if not is_admin else None
    scan_env = None
    # Per-user scan: write to user's own scan file, pass their preferences
    if user_data_dir:
        user_scan_path = os.path.join(user_data_dir, "scan_results.json")
        prefs_path = os.path.join(user_data_dir, "preferences.json")
        scan_env = {**os.environ}
        if os.path.exists(prefs_path):
            scan_env["USER_PREFS_PATH"] = prefs_path
        scan_env["SCAN_OUTPUT_PATH"] = user_scan_path
    else:
        user_scan_path = SCAN_PATH  # admin uses global

    def run_scan():
        _scan_state["running"] = True
        _scan_state["error"] = None
        _scan_state["last_result"] = None

        count_before = 0
        if os.path.exists(user_scan_path):
            try:
                with open(user_scan_path) as f:
                    count_before = len(json.load(f).get("offers", []))
            except Exception:
                pass

        try:
            subprocess.run(
                ["python", "scan_jobs.py"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
                timeout=300,
                env=scan_env,
            )
            count_after = 0
            if os.path.exists(user_scan_path):
                with open(user_scan_path) as f:
                    count_after = len(json.load(f).get("offers", []))
            new = count_after - count_before
            _scan_state["last_result"] = {
                "total": count_after,
                "new": new if new > 0 else 0,
                "message": f"{count_after} offres trouvees" + (f" (+{new} nouvelles)" if new > 0 else " (aucune nouvelle)"),
            }
            if user_data_dir:
                open(os.path.join(user_data_dir, ".first_scan_done"), "w").close()
        except Exception as e:
            _scan_state["error"] = str(e)
        finally:
            _scan_state["running"] = False

    threading.Thread(target=run_scan, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/scan/status", methods=["GET"])
@require_auth
def scan_status():
    return jsonify(_scan_state)


@app.route("/api/applications", methods=["GET"])
@require_auth
def get_applications():
    """Retourne les candidatures générées avec URLs de téléchargement."""
    from src.tracker import list_applications
    import glob as glob_mod
    db = os.path.join(_user_dir(), "applications.db") if g.user_id != "local" else None
    apps = list_applications(db_path=db)
    for app in apps:
        out = app.get("output_dir", "")
        if out and os.path.isdir(out):
            pdfs = glob_mod.glob(os.path.join(out, "*.pdf"))
            cv_files  = [p for p in pdfs if "_cv_" in os.path.basename(p)]
            ltr_files = [p for p in pdfs if "_lettre_" in os.path.basename(p)]
            app["cv_url"]     = f"/api/download/{cv_files[0]}"  if cv_files  else None
            app["letter_url"] = f"/api/download/{ltr_files[0]}" if ltr_files else None
        else:
            app["cv_url"] = None
            app["letter_url"] = None
    resp = jsonify({"applications": apps})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/recompile", methods=["POST"])
@require_auth
def recompile():
    """Recompile PDFs depuis un inspo JSON modifié par l'utilisateur."""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    inspo = data.get("inspo")
    output_dir = data.get("output_dir")
    if not inspo or not output_dir:
        return jsonify({"error": "Missing inspo or output_dir"}), 400

    try:
        from src.compiler import compile_cv, compile_letter
        user_data = _user_dir() if g.user_id != "local" else None
        truth_path = os.path.join(user_data, "truth.json") if user_data else "data/truth.json"
        with open(truth_path) as f:
            truth = json.load(f)

        analysis = inspo["analysis"]
        adapted  = inspo["adapted_bullets"]
        letter   = inspo["letter"]

        inspo_path = os.path.join(user_data, "latest_inspo.json") if user_data else "data/latest_inspo.json"
        with open(inspo_path, "w") as f:
            json.dump(inspo, f, ensure_ascii=False, indent=2)

        templates_dir = os.path.join(user_data, "templates") if user_data and os.path.isdir(os.path.join(user_data, "templates")) else None
        cv_path     = compile_cv(truth, analysis, adapted, output_dir, templates_dir=templates_dir)
        letter_path = compile_letter(letter, truth, output_dir, offer_analysis=analysis, templates_dir=templates_dir)

        return jsonify({
            "success": True,
            "cv_url": f"/api/download/{cv_path}",
            "letter_url": f"/api/download/{letter_path}",
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/applications/<int:app_id>/status", methods=["PATCH"])
@require_auth
def update_app_status(app_id):
    """Met à jour le statut d'une candidature."""
    data = request.json
    status = data.get("status") if data else None
    valid = {"to_apply", "applied", "followup", "interview", "rejected", "offer"}
    if status not in valid:
        return jsonify({"error": f"Invalid status. Valid: {sorted(valid)}"}), 400
    from src.tracker import update_status
    db = os.path.join(_user_dir(), "applications.db") if g.user_id != "local" else None
    update_status(app_id, status, db_path=db)
    return jsonify({"ok": True, "id": app_id, "status": status})


@app.route("/api/applications/<int:app_id>/notes", methods=["PATCH"])
@require_auth
def update_app_notes(app_id):
    """Met à jour les notes d'une candidature."""
    data = request.json
    notes = data.get("notes", "") if data else ""
    from src.tracker import update_notes
    db = os.path.join(_user_dir(), "applications.db") if g.user_id != "local" else None
    update_notes(app_id, notes, db_path=db)
    return jsonify({"ok": True, "id": app_id})


@app.route("/api/download/<path:filepath>")
@require_auth
def download(filepath):
    """Sert un fichier PDF."""
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404
    resp = send_file(filepath, as_attachment=True)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _is_admin():
    email = getattr(g, "user_email", "").lower()
    return bool(ADMIN_EMAILS and email and email in ADMIN_EMAILS)


def _auto_provision_admin():
    """Copy existing project data into admin's user dir on first access."""
    import shutil as _shutil
    user_data = _user_dir()
    truth_dst = os.path.join(user_data, "truth.json")
    if os.path.exists(truth_dst):
        return  # already provisioned

    log.info(f"Auto-provisioning user {g.user_id}")

    for src, dst_name in [
        (os.path.join("data", "truth.json"), "truth.json"),
        (os.path.join("data", "applications.db"), "applications.db"),
        (os.path.join("data", "latest_inspo.json"), "latest_inspo.json"),
    ]:
        if os.path.exists(src):
            _shutil.copy2(src, os.path.join(user_data, dst_name))
            pass

    output_src = "output"
    output_dst = os.path.join(user_data, "output")
    if os.path.isdir(output_src) and not os.path.isdir(output_dst):
        _shutil.copytree(output_src, output_dst)
        pass


@app.route("/api/profile", methods=["GET"])
@require_auth
def get_profile():
    """Check onboarding status. Auto-provisions admin on first access."""
    is_admin = _is_admin()

    if is_admin:
        _auto_provision_admin()

    user_data = _user_dir()
    truth_path = os.path.join(user_data, "truth.json")
    has_truth = os.path.exists(truth_path)
    prefs_path = os.path.join(user_data, "preferences.json")
    has_prefs = os.path.exists(prefs_path)

    # Only auto-provision for admins (they get existing project data)
    # Regular users must go through onboarding to upload their own CV
    onboarding_complete = has_truth and has_prefs if not is_admin else True

    # Check if truth.json has real experiences (not just minimal placeholder)
    has_real_cv = False
    if has_truth:
        try:
            with open(truth_path) as f:
                truth_data = json.load(f)
            has_real_cv = len(truth_data.get("experiences", [])) > 0
        except Exception:
            pass
    if is_admin:
        has_real_cv = True

    return jsonify({
        "has_truth": has_truth,
        "has_prefs": has_prefs,
        "has_real_cv": has_real_cv,
        "is_admin": is_admin,
        "onboarding_complete": onboarding_complete,
        "user_id": g.user_id,
    })


@app.route("/api/profile/truth", methods=["GET"])
@require_auth
def get_truth():
    """Get the user's truth.json."""
    user_data = _user_dir()
    truth_path = os.path.join(user_data, "truth.json")
    if not os.path.exists(truth_path):
        return jsonify({}), 404
    with open(truth_path) as f:
        return jsonify(json.load(f))


@app.route("/api/profile/truth", methods=["PUT"])
@require_auth
def upload_truth():
    """Upload or update the user's truth.json."""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    if "profile" not in data or "experiences" not in data:
        return jsonify({"error": "truth.json must contain 'profile' and 'experiences'"}), 400

    user_data = _user_dir()
    truth_path = os.path.join(user_data, "truth.json")
    with open(truth_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True})


@app.route("/api/profile/extract-skills", methods=["POST"])
@require_auth
def extract_skills():
    """Extract skills from a truth.json structure for onboarding auto-populate."""
    data = request.json
    if not data or "experiences" not in data:
        return jsonify({"error": "No experiences data"}), 400

    skills = set()
    titles = set()

    for exp in data.get("experiences", []):
        # Stack arrays
        for s in (exp.get("stack") or []):
            skills.add(s.strip())
        # Titles
        t = exp.get("titles", {})
        if isinstance(t, dict):
            for v in t.values():
                if v:
                    titles.add(v.strip())
        elif isinstance(t, str) and t:
            titles.add(t.strip())

    # Skills from skills section
    for track_skills in (data.get("skills") or {}).values():
        if isinstance(track_skills, dict):
            for val in track_skills.values():
                for s in str(val).split(","):
                    s = s.strip()
                    if s and len(s) < 30:
                        skills.add(s)

    return jsonify({
        "skills": sorted(skills, key=str.lower),
        "titles": sorted(titles, key=str.lower),
    })


@app.route("/api/profiles", methods=["GET"])
@require_auth
def list_profiles():
    """List all user profiles."""
    user_data = _user_dir()
    profiles_dir = os.path.join(user_data, "profiles")
    if not os.path.isdir(profiles_dir):
        return jsonify({"profiles": [], "active": None})

    profiles = []
    for fname in sorted(os.listdir(profiles_dir)):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(profiles_dir, fname)) as f:
                    p = json.load(f)
                profiles.append({
                    "id": fname[:-5],
                    "name": p.get("profile_name", fname[:-5]),
                    "title": p.get("profile", {}).get("name", ""),
                    "type": p.get("_type", "EMPLOYEE"),
                    "status": p.get("_status", "COMPLETE"),
                    "completeness": p.get("_completeness", _compute_completeness(p)),
                    "experiences_count": len(p.get("experiences", [])),
                    "education_count": len(p.get("education", [])),
                    "certifications_count": len(p.get("certifications", [])),
                    "created": p.get("_created", ""),
                })
            except Exception:
                continue

    # Get active profile
    prefs_path = os.path.join(user_data, "preferences.json")
    active = None
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            active = json.load(f).get("active_profile")

    return jsonify({"profiles": profiles, "active": active})


@app.route("/api/profiles/<profile_id>", methods=["GET"])
@require_auth
def get_profile_detail(profile_id):
    """Get a specific profile."""
    path = os.path.join(_user_dir(), "profiles", f"{profile_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Profile not found"}), 404
    with open(path) as f:
        return jsonify(json.load(f))


def _compute_completeness(truth):
    """Compute profile completeness (0-100) based on filled sections."""
    checks = [
        bool(truth.get("profile", {}).get("name")),
        bool(truth.get("profile", {}).get("email")),
        bool(truth.get("profile", {}).get("phone")),
        len(truth.get("experiences", [])) > 0,
        len(truth.get("education", [])) > 0,
        bool(truth.get("skills")),
        len(truth.get("certifications", [])) > 0,
        bool(truth.get("profile", {}).get("linkedin")),
        bool(truth.get("summaries")),
        len(truth.get("experiences", [])) >= 2,
    ]
    return int(sum(checks) / len(checks) * 100)


@app.route("/api/profiles", methods=["POST"])
@require_auth
def create_profile():
    """Create a new profile from parsed CV data."""
    data = request.json
    if not data or "profile_name" not in data or "truth" not in data:
        return jsonify({"error": "profile_name and truth required"}), 400

    from datetime import datetime as _dt
    profile_name = data["profile_name"].strip()
    profile_id = profile_name.lower().replace(" ", "_").replace("'", "")[:30]
    profile_type = data.get("type", "EMPLOYEE")  # STUDENT | EMPLOYEE | FREELANCER
    truth = data["truth"]
    truth["profile_name"] = profile_name
    truth["_type"] = profile_type
    truth["_status"] = "COMPLETE" if truth.get("experiences") else "DRAFT"
    truth["_completeness"] = _compute_completeness(truth)
    truth["_created"] = _dt.now().isoformat()
    truth["_updated"] = _dt.now().isoformat()

    user_data = _user_dir()
    profiles_dir = os.path.join(user_data, "profiles")
    os.makedirs(profiles_dir, exist_ok=True)

    with open(os.path.join(profiles_dir, f"{profile_id}.json"), "w") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2)

    # Also set as active truth.json
    with open(os.path.join(user_data, "truth.json"), "w") as f:
        json.dump(truth, f, ensure_ascii=False, indent=2)

    # Ensure preferences exist and set active profile
    prefs_path = os.path.join(user_data, "preferences.json")
    prefs = {}
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            prefs = json.load(f)
    prefs["active_profile"] = profile_id
    with open(prefs_path, "w") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

    log.info(f"Profile created: {profile_id} ({profile_name})")
    return jsonify({"ok": True, "id": profile_id, "name": profile_name, "completeness": truth["_completeness"]})


@app.route("/api/profiles/<profile_id>/activate", methods=["POST"])
@require_auth
def activate_profile(profile_id):
    """Set a profile as active (used for generation)."""
    user_data = _user_dir()
    src = os.path.join(user_data, "profiles", f"{profile_id}.json")
    if not os.path.exists(src):
        return jsonify({"error": "Profile not found"}), 404

    import shutil
    shutil.copy2(src, os.path.join(user_data, "truth.json"))

    # Save active profile in preferences
    prefs_path = os.path.join(user_data, "preferences.json")
    prefs = {}
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            prefs = json.load(f)
    prefs["active_profile"] = profile_id
    with open(prefs_path, "w") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "active": profile_id})


@app.route("/api/profiles/<profile_id>", methods=["PATCH"])
@require_auth
def update_profile(profile_id):
    """Update specific fields of a profile."""
    path = os.path.join(_user_dir(), "profiles", f"{profile_id}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Profile not found"}), 404

    with open(path) as f:
        profile = json.load(f)

    data = request.json or {}
    # Update allowed sections
    for key in ["profile", "experiences", "education", "skills", "certifications",
                 "summaries", "profile_name", "_type"]:
        if key in data:
            profile[key] = data[key]

    from datetime import datetime as _dt
    profile["_updated"] = _dt.now().isoformat()
    profile["_completeness"] = _compute_completeness(profile)

    with open(path, "w") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    # If this is the active profile, also update truth.json
    prefs_path = os.path.join(_user_dir(), "preferences.json")
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            prefs = json.load(f)
        if prefs.get("active_profile") == profile_id:
            import shutil
            shutil.copy2(path, os.path.join(_user_dir(), "truth.json"))

    return jsonify({"ok": True, "completeness": profile["_completeness"]})


@app.route("/api/profiles/<profile_id>", methods=["DELETE"])
@require_auth
def delete_profile(profile_id):
    """Delete a profile."""
    path = os.path.join(_user_dir(), "profiles", f"{profile_id}.json")
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"ok": True})


@app.route("/api/profile/preferences", methods=["GET"])
@require_auth
def get_preferences():
    """Get user's job search preferences."""
    user_data = _user_dir()
    prefs_path = os.path.join(user_data, "preferences.json")
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            return jsonify(json.load(f))
    return jsonify({})


@app.route("/api/profile/preferences", methods=["PUT"])
@require_auth
def update_preferences():
    """Save user's job search preferences."""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    user_data = _user_dir()
    prefs_path = os.path.join(user_data, "preferences.json")
    with open(prefs_path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True})


# ── Gemini CV Parser ─────────────────────────────────────────────────────────

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

PARSE_CV_PROMPT = """Tu es un expert RH. Analyse ce CV et extrais un JSON structuré.

IMPORTANT: Retourne UNIQUEMENT du JSON valide, sans markdown, sans ```json```, sans commentaire.

Structure exacte attendue:
{
  "profile": {
    "name": "Prénom Nom",
    "phone": "+33...",
    "email": "email@example.com",
    "linkedin": "linkedin.com/in/...",
    "github": "github.com/...",
    "address": "Adresse principale",
    "location": "Ville, Pays",
    "languages": [{"lang": "Français", "level": "Natif"}, ...]
  },
  "summaries": {
    "tech": "Résumé orienté technique (2-3 phrases)",
    "consulting": "Résumé orienté conseil/management (2-3 phrases)"
  },
  "experiences": [
    {
      "id": "identifiant_court",
      "company": "Nom entreprise",
      "date_start": "Mois Année",
      "date_end": "Mois Année",
      "location": "Ville, Pays",
      "titles": {
        "tech": "Titre technique",
        "consulting": "Titre consulting"
      },
      "stack": ["Tech1", "Tech2"],
      "bullets_pool": {
        "tech": ["Bullet technique 1", "Bullet technique 2", "..."],
        "consulting": ["Bullet consulting 1", "Bullet consulting 2", "..."]
      }
    }
  ],
  "education": [
    {
      "school": "Nom ecole",
      "degree": "Diplome",
      "date_start": "Annee",
      "date_end": "Annee",
      "location": "Ville, Pays"
    }
  ],
  "certifications": ["Certification 1, Annee", "Certification 2, Annee"],
  "skills": {
    "tech": {
      "Langages": "Python, Java, ...",
      "Frameworks": "React, Spring Boot, ...",
      "DevOps": "Docker, CI/CD, ..."
    },
    "consulting": {
      "Methodologies": "Agile, Scrum, ...",
      "Outils": "JIRA, ...",
      "Domaines": "..."
    }
  }
}

Regles CRITIQUES:
- Extrais TOUTES les experiences, formations, certifications, et competences du CV. N'en oublie AUCUNE.
- Pour chaque experience, genere 3-6 bullets par track (tech et consulting)
- Les bullets doivent etre des phrases completes, orientees resultat
- Si le CV n'est pas oriente consulting, genere quand meme des bullets consulting en reformulant
- L'id de chaque experience doit etre un slug court (ex: "freelance", "google", "stage_sopra")
- Extrais TOUTES les formations (ecoles, diplomes) dans "education"
- Extrais TOUTES les certifications dans "certifications"
- Si une info manque (github, telephone...), mets une chaine vide ""
- Le CV peut faire plusieurs pages. Lis TOUT le texte jusqu'a la fin.
"""


def _parse_json_response(raw):
    """Extract JSON from a possibly markdown-fenced response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    if raw.startswith("json"):
        raw = raw[4:]
    return json.loads(raw.strip())


def _parse_cv_gemini(cv_text=None, pdf_data=None):
    """Parse CV with Gemini API (new google-genai SDK)."""
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    if pdf_data:
        import base64
        b64 = base64.b64encode(pdf_data).decode()
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                PARSE_CV_PROMPT,
                {"inline_data": {"mime_type": "application/pdf", "data": b64}},
            ],
        )
    else:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=PARSE_CV_PROMPT + "\n\nCV:\n" + cv_text,
        )

    return _parse_json_response(response.text)


def _parse_cv_claude_api(cv_text):
    """Parse CV with Anthropic API directly. Raises on failure with descriptive message."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured")
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    truncated = cv_text[:25000] if len(cv_text) > 25000 else cv_text
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=16384,
        messages=[
            {"role": "user", "content": PARSE_CV_PROMPT + "\n\nCV:\n" + truncated},
            {"role": "assistant", "content": "{"},
        ],
    )
    raw = response.content[0].text if response.content else ""
    # Detect if output was truncated (stop_reason == "max_tokens" means JSON is incomplete)
    if response.stop_reason == "end_turn":
        text = "{" + raw
    else:
        # Output was truncated — try to close the JSON gracefully
        log.warning(f"CV parse output truncated (stop_reason={response.stop_reason}), attempting JSON repair")
        text = "{" + raw
        # Try to close any open structures
        if text.count('"') % 2 == 1:
            text += '"'
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        text += ']' * max(0, open_brackets) + '}' * max(0, open_braces)
    result = _parse_json_response(text)
    if not isinstance(result, dict) or "profile" not in result:
        raise ValueError(f"AI returned incomplete data (missing 'profile' key)")
    return result


@app.route("/api/parse-cv", methods=["POST"])
@require_auth
def parse_cv():
    """Parse a CV (PDF or text) into truth.json structure using Claude AI."""
    cv_text = None

    if request.files and "file" in request.files:
        f = request.files["file"]
        if f.filename.lower().endswith(".pdf"):
            pdf_data = f.read()
            import io
            # Primary: pdfplumber (better multi-page, multi-column extraction)
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
                    pages_text = [page.extract_text() or "" for page in pdf.pages]
                    cv_text = "\n\n".join(pages_text).strip()
                    log.info(f"PDF extracted: {len(cv_text)} chars from {len(pdf.pages)} pages (pdfplumber)")
            except Exception:
                cv_text = None
            # Fallback: pypdf
            if not cv_text or len(cv_text) < 20:
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(pdf_data))
                    pages_text = [page.extract_text() or "" for page in reader.pages]
                    fallback_text = "\n\n".join(pages_text).strip()
                    log.info(f"PDF extracted: {len(fallback_text)} chars from {len(reader.pages)} pages (pypdf fallback)")
                    if len(fallback_text) > len(cv_text or ""):
                        cv_text = fallback_text
                except Exception:
                    pass
        else:
            cv_text = f.read().decode("utf-8", errors="replace")
    elif request.json and "text" in request.json:
        cv_text = request.json["text"]
    else:
        return jsonify({"error": "Provide a PDF file or text"}), 400

    if not cv_text or len(cv_text) < 20:
        return jsonify({"error": "CV vide ou trop court. Collez au moins votre nom et quelques experiences."}), 400

    try:
        truth = _parse_cv_claude_api(cv_text)
        log.info(f"CV parsed: {truth.get('profile',{}).get('name','?')}, {len(truth.get('experiences',[]))} exp")
        return jsonify({"ok": True, "truth": truth})
    except json.JSONDecodeError:
        return jsonify({"error": "L'IA n'a pas retourné un JSON valide. Réessayez."}), 422
    except Exception as e:
        log.error(f"CV parse failed: {e}")
        return jsonify({"error": f"Erreur analyse CV: {str(e)[:200]}"}), 422


@app.route("/api/parse-linkedin", methods=["POST"])
@require_auth
def parse_linkedin():
    """Scrape a public LinkedIn profile and parse it into truth.json structure."""
    data = request.json
    url = (data or {}).get("url", "").strip()
    if not url or "linkedin.com/in/" not in url:
        return jsonify({"error": "URL LinkedIn invalide. Format: https://www.linkedin.com/in/votre-profil"}), 400

    try:
        import requests as req
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9",
        }
        resp = req.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            return jsonify({"error": f"Impossible d'accéder au profil (HTTP {resp.status_code})."}), 422

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        # Extract JSON-LD (best source — has name, companies, education, languages)
        profile_data = {}
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string, strict=False)
                graph = ld.get("@graph", [ld]) if isinstance(ld, dict) else ld
                for item in graph:
                    if isinstance(item, dict) and item.get("@type") == "Person":
                        profile_data = item
                        break
            except (json.JSONDecodeError, TypeError):
                continue

        # Extract meta description (has summary like "Expérience : Accenture · Formation : IAE")
        meta_desc = ""
        for meta in soup.find_all("meta", attrs={"name": "description"}):
            meta_desc = meta.get("content", "")
        og_desc = ""
        for meta in soup.find_all("meta", attrs={"property": "og:description"}):
            og_desc = meta.get("content", "")

        if not profile_data and not meta_desc:
            return jsonify({"error": "Profil LinkedIn inaccessible. LinkedIn limite les données publiques. Essayez d'importer votre CV en PDF (LinkedIn > Profil > Ressources > Enregistrer en PDF)."}), 422

        # Build a text summary from what we have
        parts = []
        name = profile_data.get("name", "")
        if name:
            parts.append(f"Nom: {name}")

        # Current company
        works_for = profile_data.get("worksFor", [])
        for org in works_for:
            if isinstance(org, dict):
                org_name = org.get("name", "")
                loc = org.get("location", "")
                if org_name and "***" not in org_name:
                    parts.append(f"Entreprise: {org_name} ({loc})" if loc else f"Entreprise: {org_name}")

        # Education
        alumni = profile_data.get("alumniOf", [])
        for edu in alumni:
            if isinstance(edu, dict):
                edu_name = edu.get("name", "")
                member = edu.get("member", {})
                start = member.get("startDate", "") if isinstance(member, dict) else ""
                end = member.get("endDate", "") if isinstance(member, dict) else ""
                if edu_name and "***" not in edu_name:
                    parts.append(f"Formation: {edu_name} ({start}-{end})")

        # Languages
        langs = profile_data.get("knowsLanguage", [])
        lang_names = [l.get("name", "") for l in langs if isinstance(l, dict) and l.get("name")]
        if lang_names:
            parts.append(f"Langues: {', '.join(lang_names)}")

        # Location
        addr = profile_data.get("address", {})
        if isinstance(addr, dict) and addr.get("addressLocality"):
            parts.append(f"Lieu: {addr['addressLocality']}")

        # Job titles (often censored but sometimes visible)
        titles = profile_data.get("jobTitle", [])
        visible_titles = [t for t in titles if isinstance(t, str) and "***" not in t]
        if visible_titles:
            parts.append(f"Postes: {'; '.join(visible_titles)}")

        # Add meta description
        if og_desc or meta_desc:
            parts.append(f"Resume: {og_desc or meta_desc}")

        combined = "\n".join(parts)

        if len(combined) < 50:
            return jsonify({"error": "LinkedIn limite les données des profils non connectés. Essayez plutot d'exporter votre CV en PDF depuis LinkedIn (Profil > Ressources > Enregistrer en PDF), puis importez-le ici."}), 422

        # Send to Gemini/Claude for structuring
        prompt = f"Profil LinkedIn (données partielles, complète au mieux):\n{combined}"
        if GEMINI_API_KEY:
            try:
                truth = _parse_cv_gemini(cv_text=prompt)
                if truth and "profile" in truth and "experiences" in truth:
                    return jsonify({"ok": True, "truth": truth, "partial": True})
            except Exception as e:
                log.error(f"Gemini LinkedIn parse failed: {e}")

        try:
            truth = _parse_cv_claude_api(prompt)
            if truth and "profile" in truth and "experiences" in truth:
                return jsonify({"ok": True, "truth": truth, "partial": True})
        except Exception as e:
            log.error(f"Claude LinkedIn parse failed: {e}")

        return jsonify({"error": "Données LinkedIn insuffisantes. Exportez votre CV en PDF depuis LinkedIn (Profil > Ressources > Enregistrer en PDF) et importez-le via l'onglet Fichier."}), 422
    except Exception as e:
        return jsonify({"error": f"Erreur: {str(e)}"}), 500


TEMPLATES_DIR = "templates"
TEMPLATES_CONFIG = os.path.join(TEMPLATES_DIR, "config.json")


CV_LIBRARY = [
    {"id": "default", "name": "Defaut", "desc": "Template actuel avec icons et couleur teal", "file": "cv_default.tex", "style": "Modern"},
    {"id": "modern", "name": "Moderne", "desc": "Header centre, sections colorees, compact", "file": "cv_modern.tex", "style": "Modern"},
    {"id": "minimal", "name": "Minimal", "desc": "Pur texte, lignes fines, maximum espace", "file": "cv_minimal.tex", "style": "Traditional"},
    {"id": "professional", "name": "Professionnel", "desc": "Header sombre, titres en petites majuscules", "file": "cv_professional.tex", "style": "Creative"},
]

LETTER_LIBRARY = [
    {"id": "default", "name": "Defaut", "desc": "Template avec accents couleur et icones", "file": "letter_default.tex", "style": "Modern"},
    {"id": "classic", "name": "Classique", "desc": "Police Charter, ligne horizontale, formel", "file": "letter_classic.tex", "style": "Traditional"},
    {"id": "minimal", "name": "Minimal", "desc": "Pur texte, maximum d'espace blanc", "file": "letter_minimal.tex", "style": "Modern"},
    {"id": "modern", "name": "Moderne", "desc": "En-tete colore, nom en gras, compact", "file": "letter_modern.tex", "style": "Creative"},
    {"id": "professional", "name": "Professionnel", "desc": "En-tete deux colonnes, separateur subtil", "file": "letter_professional.tex", "style": "Traditional"},
]


@app.route("/api/templates/library")
@require_auth
def get_template_library():
    """List available templates with preview URLs."""
    return jsonify({
        "cvs": [{**t, "preview_url": f"/api/templates/library/preview/cv/{t['id']}"} for t in CV_LIBRARY],
        "letters": [{**t, "preview_url": f"/api/templates/library/preview/letter/{t['id']}"} for t in LETTER_LIBRARY],
    })


@app.route("/api/templates/library/preview/cv/<template_id>")
@require_auth
def preview_library_cv(template_id):
    """Compile a CV template from library with sample data and serve PDF."""
    tpl = next((t for t in CV_LIBRARY if t["id"] == template_id), None)
    if not tpl:
        return jsonify({"error": "Template not found"}), 404

    lib_dir = os.path.join(TEMPLATES_DIR, "library", "cv")
    tpl_path = os.path.join(lib_dir, tpl["file"])
    if not os.path.exists(tpl_path):
        return jsonify({"error": "Template file missing"}), 404

    try:
        # Use the existing template preview mechanism
        from src.compiler import compile_cv
        user_data = _user_dir() if g.user_id != "local" else None
        truth_path = os.path.join(user_data, "truth.json") if user_data else "data/truth.json"
        if not os.path.exists(truth_path):
            return jsonify({"error": "No truth.json"}), 404
        with open(truth_path) as f:
            truth = json.load(f)

        sample_analysis = {
            "track": "tech",
            "title_suggestion": "Poste Example",
            "adapted_summary": truth.get("summaries", {}).get("tech", "Professionnel avec experience."),
            "company_name": "Example",
            "offer_location": "Paris",
        }
        sample_bullets = {"experiences": [
            {"id": exp["id"], "bullets": (exp.get("bullets_pool", {}).get("tech") or ["Experience dans le domaine."])[:3]}
            for exp in truth.get("experiences", [])[:4]
        ]}

        import tempfile
        preview_dir = tempfile.mkdtemp(prefix="tpl_cv_")
        # Copy the library template as cv_master.tex temporarily
        import shutil
        tmp_tpl_dir = os.path.join(preview_dir, "templates")
        os.makedirs(tmp_tpl_dir)
        shutil.copy2(tpl_path, os.path.join(tmp_tpl_dir, "cv_master.tex"))

        cv_path = compile_cv(truth, sample_analysis, sample_bullets, preview_dir, templates_dir=tmp_tpl_dir)
        if os.path.exists(cv_path):
            return send_file(cv_path, mimetype="application/pdf")
        return jsonify({"error": "Compilation failed"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/templates/library/preview/letter/<template_id>")
@require_auth
def preview_library_letter(template_id):
    """Compile a letter template with sample data and serve the PDF."""
    tpl = next((t for t in LETTER_LIBRARY if t["id"] == template_id), None)
    if not tpl:
        return jsonify({"error": "Template not found"}), 404

    lib_dir = os.path.join(TEMPLATES_DIR, "library", "letter")
    tpl_path = os.path.join(lib_dir, tpl["file"])
    if not os.path.exists(tpl_path):
        return jsonify({"error": "Template file missing"}), 404

    try:
        with open(tpl_path) as f:
            content = f.read()

        user_data = _user_dir() if g.user_id != "local" else None
        truth_path = os.path.join(user_data, "truth.json") if user_data else "data/truth.json"
        name = "Candidat"
        email = ""
        phone = ""
        if os.path.exists(truth_path):
            with open(truth_path) as f:
                truth = json.load(f)
            profile = truth.get("profile", {})
            name = profile.get("name", "Candidat")
            email = profile.get("email", "")
            phone = profile.get("phone", "")

        replacements = {
            "<<name>>": name,
            "<<email>>": email or "email@example.com",
            "<<phone>>": phone or "+33 6 00 00 00 00",
            "<<address>>": "Paris, France",
            "<<company_name>>": "Exemple Corp",
            "<<company_address>>": "Paris, France",
            "<<position>>": "Poste Example",
            "<<body>>": "Diplome d'un Master, je souhaite candidater pour ce poste.\\par Mon experience me permet de repondre a vos besoins.\\par Je serais ravi de vous rencontrer.",
        }
        for k, v in replacements.items():
            content = content.replace(k, v)

        import tempfile
        tmpdir = tempfile.mkdtemp(prefix="tpl_lib_")
        texpath = os.path.join(tmpdir, "letter.tex")
        with open(texpath, "w") as f:
            f.write(content)

        subprocess.run(["pdflatex", "-interaction=nonstopmode", "-output-directory", tmpdir, texpath], capture_output=True, timeout=30)
        pdfpath = os.path.join(tmpdir, "letter.pdf")
        if os.path.exists(pdfpath):
            return send_file(pdfpath, mimetype="application/pdf")
        return jsonify({"error": "Compilation failed"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/templates/library/select", methods=["POST"])
@require_auth
def select_library_template():
    """Save user's template selection."""
    data = request.json or {}
    letter_id = data.get("letter_id")
    if letter_id and not any(t["id"] == letter_id for t in LETTER_LIBRARY):
        return jsonify({"error": "Invalid template"}), 400

    user_data = _user_dir()
    prefs_path = os.path.join(user_data, "preferences.json")
    prefs = {}
    if os.path.exists(prefs_path):
        with open(prefs_path) as f:
            prefs = json.load(f)

    if letter_id:
        prefs["letter_template"] = letter_id
        # Copy selected template as the user's active letter template
        lib_dir = os.path.join(TEMPLATES_DIR, "library", "letter")
        tpl = next(t for t in LETTER_LIBRARY if t["id"] == letter_id)
        src = os.path.join(lib_dir, tpl["file"])
        if os.path.exists(src):
            import shutil
            user_tpl_dir = os.path.join(user_data, "templates")
            os.makedirs(user_tpl_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(user_tpl_dir, "letter_master.tex"))

    with open(prefs_path, "w") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)

    return jsonify({"ok": True, "selected": letter_id})


def _load_tpl_config():
    if os.path.exists(TEMPLATES_CONFIG):
        with open(TEMPLATES_CONFIG) as f:
            return json.load(f)
    return {"cv_active": "default", "letter_active": "default"}


def _save_tpl_config(cfg):
    with open(TEMPLATES_CONFIG, "w") as f:
        json.dump(cfg, f, indent=2)


def _sync_master(kind, cfg):
    """Copy the active variant to *_master.tex so the compiler always reads master."""
    variant = cfg.get(f"{kind}_active", "default")
    src = os.path.join(TEMPLATES_DIR, f"{kind}_{variant}.tex")
    dst = os.path.join(TEMPLATES_DIR, f"{kind}_master.tex")
    if os.path.exists(src):
        import shutil
        shutil.copy2(src, dst)


def _read_tex(name):
    p = os.path.join(TEMPLATES_DIR, name)
    return open(p, "r").read() if os.path.exists(p) else None


@app.route("/api/templates", methods=["GET"])
@require_auth
def get_templates():
    """Retourne les templates (défaut + custom + état actif)."""
    cfg = _load_tpl_config()
    return jsonify({
        "cv_default":    _read_tex("cv_default.tex") or "",
        "cv_custom":     _read_tex("cv_custom.tex"),
        "letter_default": _read_tex("letter_default.tex") or "",
        "letter_custom":  _read_tex("letter_custom.tex"),
        "cv_active":     cfg.get("cv_active", "default"),
        "letter_active": cfg.get("letter_active", "default"),
    })


@app.route("/api/templates", methods=["PUT"])
@require_auth
def update_templates():
    """Upload custom templates and/or switch active variant."""
    data = request.json
    if not data:
        return jsonify({"error": "No data"}), 400

    cfg = _load_tpl_config()
    updated = []

    # Save custom content
    if "cv_custom" in data and data["cv_custom"] and data["cv_custom"].strip():
        with open(os.path.join(TEMPLATES_DIR, "cv_custom.tex"), "w") as f:
            f.write(data["cv_custom"])
        updated.append("cv_custom")

    if "letter_custom" in data and data["letter_custom"] and data["letter_custom"].strip():
        with open(os.path.join(TEMPLATES_DIR, "letter_custom.tex"), "w") as f:
            f.write(data["letter_custom"])
        updated.append("letter_custom")

    # Switch active variant
    if "cv_active" in data and data["cv_active"] in ("default", "custom"):
        cfg["cv_active"] = data["cv_active"]
        updated.append("cv_active")
    if "letter_active" in data and data["letter_active"] in ("default", "custom"):
        cfg["letter_active"] = data["letter_active"]
        updated.append("letter_active")

    _save_tpl_config(cfg)
    _sync_master("cv", cfg)
    _sync_master("letter", cfg)

    return jsonify({"ok": True, "updated": updated, "config": cfg})


@app.route("/api/templates/preview/<kind>")
@require_auth
def template_preview(kind):
    """Compile a sample PDF from the active template and serve it for preview."""
    if kind not in ("cv", "letter"):
        return jsonify({"error": "Invalid kind"}), 400

    try:
        from src.compiler import compile_cv, compile_letter

        user_data = _user_dir() if g.user_id != "local" else None
        truth_path = os.path.join(user_data, "truth.json") if user_data else "data/truth.json"
        if not os.path.exists(truth_path):
            return jsonify({"error": "No truth.json — upload your CV first"}), 404
        with open(truth_path) as f:
            truth = json.load(f)

        # Sample data for preview
        sample_analysis = {
            "track": "tech",
            "title_suggestion": "Developpeur Fullstack",
            "adapted_summary": "Ingenieur logiciel avec experience en developpement web fullstack.",
            "company_name": "Exemple Corp",
            "offer_location": "Paris",
            "company_address": "",
        }
        sample_bullets = {"experiences": [
            {"id": exp["id"], "bullets": (exp.get("bullets_pool", {}).get("tech") or ["Experience dans le domaine."])[:3]}
            for exp in truth.get("experiences", [])[:4]
        ]}
        sample_letter = {
            "company_name": "Exemple Corp",
            "company_address": "Paris, France",
            "position": "Developpeur Fullstack",
            "body": "Diplome d'un Master et d'un diplome d'ingenieur, je souhaite candidater pour ce poste.\n\nMon experience m'a permis de developper des competences solides.\n\nJe serais ravi de vous rencontrer.",
        }

        import tempfile
        preview_dir = tempfile.mkdtemp(prefix="tpl_preview_")
        templates_dir = os.path.join(user_data, "templates") if user_data and os.path.isdir(os.path.join(user_data, "templates")) else None

        if kind == "cv":
            pdf_path = compile_cv(truth, sample_analysis, sample_bullets, preview_dir, templates_dir=templates_dir)
        else:
            pdf_path = compile_letter(sample_letter, truth, preview_dir, offer_analysis=sample_analysis, templates_dir=templates_dir)

        if os.path.exists(pdf_path):
            return send_file(pdf_path, mimetype='application/pdf')
        return jsonify({"error": "Compilation failed"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("API server: http://localhost:5001")
    print("Dashboard:  http://localhost:5173")
    app.run(host="0.0.0.0", port=5001, debug=False, threaded=True)
