# Job Apply Tool — Guide d'utilisation

## Démarrage (une fois par session)

Ouvre deux onglets terminal dans `~/Documents/mass` :

**Terminal 1 — Backend**
```bash
cd ~/Documents/mass
source venv/bin/activate
python server.py
```

**Terminal 2 — Dashboard**
```bash
cd ~/Documents/mass/dashboard
npm run dev
```

Ouvre le dashboard : http://localhost:5173

---

## Workflow quotidien

### 1. Scanner les nouvelles offres
- Clique sur le bouton **Scanner** en haut à droite du dashboard
- Le bouton tourne pendant ~2 minutes
- Toast en bas : "X offres trouvées (+Y nouvelles)" ou "aucune nouvelle"

### 2. Lire et filtrer les offres
- Cartes triées par : fraîcheur → XP requis (0 en premier) → score
- **Badge NEW** (indigo) = publié aujourd'hui
- **Fond orange** = déjà généré
- Clique sur le titre ou "Voir l'offre" pour ouvrir l'offre originale
- Filtres disponibles : métier, ville, contrat, score minimum, source

### 3. Générer CV + Lettre

**Option A — Depuis le dashboard (automatique)**
1. Clique sur **Générer CV + Lettre** sur une carte
2. Toast jaune : "Génération en cours… (~30s)"
3. ~30-60 secondes plus tard : toast vert + boutons **CV** et **Lettre** apparaissent
4. Clique pour télécharger directement

**Option B — Depuis le chat Claude (meilleur résultat)**
1. Copie le titre + description de l'offre
2. Colle-la dans le chat Claude Code
3. Claude génère `data/latest_inspo.json` avec bullets réécrits + lettre sur mesure
4. Dans le terminal :
```bash
cd ~/Documents/mass
./gen
```
5. Le dossier `output/[company]_[date]/` s'ouvre automatiquement

---

## Commandes utiles

| Commande | Usage |
|---|---|
| `python server.py` | Lance le backend API (port 5001) |
| `python scan_jobs.py` | Lance le scan manuellement (terminal) |
| `./gen` | Compile CV + Lettre depuis `latest_inspo.json` |
| `python compile_from_json.py` | Idem (version longue) |

---

## Structure des fichiers générés

```
output/
└── [company]_[titre]_[date]/
    ├── omarajraoui_cv_[company].pdf
    ├── omarajraoui_lettre_[company].pdf
    ├── omarajraoui_cv_[company].tex
    ├── omarajraoui_lettre_[company].tex
    └── summary.json
```

---

## Sources scannées

| Source | Volume | Fiabilité |
|---|---|---|
| Welcome to the Jungle (WTTJ) | ~60-80 offres | Très bonne |
| France Travail | ~10-20 offres | Bonne |
| LinkedIn (guest API) | ~40-70 offres | Bonne |
| Choisir le Service Public (CSP) | ~5-15 offres IT | Bonne (public uniquement) |

Filtres appliqués automatiquement :
- CDI/CDD uniquement (pas de stage/alternance)
- France uniquement
- 0-3 ans d'expérience max
- Publiés dans les 7 derniers jours
- Mots exclus : "senior", "confirmé", "lead"

---

## Si ça ne marche pas

**Dashboard vide ou date ancienne**
```bash
# Relancer le backend
lsof -i :5001 -t | xargs kill
source venv/bin/activate && python server.py
```

**Bouton Générer sans réponse**
- Vérifie que `python server.py` tourne dans un terminal
- Recharge le dashboard avec Cmd+Shift+R

**pdflatex introuvable**
```bash
export PATH="/usr/local/texlive/2026basic/bin/universal-darwin:$PATH"
./gen
```

**Scan qui ne se lance pas**
```bash
source venv/bin/activate
python scan_jobs.py
```
