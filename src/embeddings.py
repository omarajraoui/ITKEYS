"""
Semantic scoring with sentence embeddings.
Uses all-MiniLM-L6-v2 for fast, free, local embeddings.
"""

import os
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'

import numpy as np

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('all-MiniLM-L6-v2', token=False)
        print("[embeddings] Model loaded")
    return _model


def embed_texts(texts):
    """Embed a list of texts. Returns numpy array of shape (n, 384)."""
    model = _get_model()
    return model.encode(texts, show_progress_bar=False, normalize_embeddings=True)


def build_profile_embedding(prefs):
    """Build a single embedding vector from user preferences."""
    parts = []
    if prefs.get("current_title"):
        parts.append(prefs["current_title"])
    for t in (prefs.get("titles_target") or []):
        parts.append(t)
    for s in (prefs.get("skills_core") or []):
        parts.append(s)
    for s in (prefs.get("skills_secondary") or [])[:5]:
        parts.append(s)

    if not parts:
        return None

    text = " ".join(parts)
    return embed_texts([text])[0]


def score_offers_semantic(offers, profile_embedding, weight=50):
    """Score offers by cosine similarity with profile embedding.

    Returns dict: offer_url -> semantic_score (0-100).
    weight controls how much semantic score contributes (default 50 = half the final score).
    """
    if profile_embedding is None or not offers:
        return {}

    # Build offer texts
    texts = []
    urls = []
    for o in offers:
        t = f"{o.get('title', '')} {o.get('company', '')} {o.get('description', '')[:500]}"
        texts.append(t)
        urls.append(o.get('url', ''))

    offer_embeddings = embed_texts(texts)

    # Cosine similarity (embeddings are already normalized)
    sims = np.dot(offer_embeddings, profile_embedding)

    # Scale to 0-100
    scores = {}
    for url, sim in zip(urls, sims):
        # sim is typically 0.05-0.70 for relevant matches
        # Map to 0-weight range
        normalized = max(0, min(1, (sim - 0.05) / 0.60))  # 0.05-0.65 -> 0-1
        scores[url] = int(normalized * weight)

    return scores
