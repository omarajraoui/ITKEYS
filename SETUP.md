# ITKeys / Mass Apply — Team Setup Guide

## Quick Start

### 1. Clone & Branch

```bash
git clone <repo-url>
cd mass
git checkout <your-branch>   # zakaria, omar, or khalid
```

### 2. Backend Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pdfplumber   # for multi-page PDF parsing
```

### 3. Environment Variables

```bash
cp .env.example .env
# Fill in your values (see below)
```

Required variables:
| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for CV parsing and generation |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase anon/public key |
| `SUPABASE_JWT_SECRET` | Yes | Supabase JWT secret (Settings > API) |
| `ADZUNA_APP_ID` | No | Adzuna job API app ID |
| `ADZUNA_APP_KEY` | No | Adzuna job API key |
| `ADMIN_EMAILS` | No | Comma-separated admin emails |

### 4. Frontend Setup

```bash
cd dashboard
npm install
```

Create `dashboard/.env`:
```
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ...
```

### 5. Run

```bash
# Terminal 1 — Backend (from project root)
source venv/bin/activate
python server.py
# → http://localhost:5001

# Terminal 2 — Frontend
cd dashboard
npm run dev
# → http://localhost:5173
```

---

## Project Structure

```
mass/
├── server.py                 # Flask API server (all endpoints)
├── dashboard/
│   ├── src/App.jsx           # React SPA (single file)
│   ├── src/Auth.jsx           # Supabase auth provider
│   ├── src/supabase.js       # Supabase client init
│   └── vite.config.js        # Vite config (proxies /api → :5001)
├── src/
│   ├── generator.py          # CV + letter generation (Claude AI)
│   ├── scoring.py            # Job offer scoring engine
│   ├── compiler/             # LaTeX → PDF compilation
│   ├── scraper/              # Job scrapers (WTTJ, FranceTravail, Adzuna)
│   └── tracker.py            # SQLite application tracker
├── templates/
│   ├── cv_master.tex         # LaTeX CV template
│   └── letter_master.tex     # LaTeX letter template
├── data/
│   └── truth.json            # Admin profile (source of truth)
└── .env.example              # Environment template
```

---

## Architecture

### Authentication
- **Supabase Auth** — email/password or magic link
- Frontend gets JWT via `supabase.auth.getSession()`
- Backend validates via `@require_auth` decorator (3 fallback levels)
- Per-user data isolated in `data/users/{user_id}/`

### Multi-Profile System
- Each user can have multiple profiles (e.g., "Dev Fullstack", "Data Engineer")
- Profiles stored in `data/users/{uid}/profiles/{profile_id}.json`
- Active profile copied to `data/users/{uid}/truth.json`
- Active profile ID stored in `data/users/{uid}/preferences.json`

### Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/profile` | Get current user profile metadata |
| `GET` | `/api/profile/truth` | Get active profile data |
| `PUT` | `/api/profile/truth` | Update active profile data |
| `GET` | `/api/profiles` | List all user profiles |
| `POST` | `/api/profiles` | Create new profile |
| `POST` | `/api/profiles/:id/activate` | Switch active profile |
| `POST` | `/api/parse-cv` | Upload & parse CV (PDF/text) |
| `GET` | `/api/offers` | Get scored job offers |
| `POST` | `/api/scan` | Trigger job scan |
| `POST` | `/api/generate` | Generate CV + letter for an offer (SSE) |
| `GET/PUT` | `/api/profile/preferences` | Job search preferences |

### CV Parsing Flow
1. User uploads PDF → `POST /api/parse-cv`
2. `pdfplumber` extracts text from ALL pages (fallback: `pypdf`)
3. Text sent to Claude Haiku → structured JSON (profile, experiences, education, skills)
4. Frontend displays extracted data for review
5. User clicks "Create" → `POST /api/profiles` with parsed data

### Job Scoring
- Each offer evaluated across 6 dimensions (role fit, skill fit, experience, seniority, location, contract)
- Produces recommendation: `STRONG_APPLY`, `APPLY`, `STRETCH`, `LOW_PRIORITY`, `REJECT`
- Scoring based on user preferences (skills, titles, cities, experience level)

---

## Git Workflow

### Branches
| Branch | Owner | Focus |
|--------|-------|-------|
| `main` | — | Stable, reviewed code only |
| `zakaria` | Zakaria | |
| `omar` | Omar | |
| `khalid` | Khalid | |

### Rules
1. **Never push directly to `main`** — always PR from your branch
2. Pull `main` into your branch before starting work: `git pull origin main`
3. Keep commits focused — one feature or fix per commit
4. Test before pushing: `cd dashboard && npm run build`

### Daily Flow
```bash
git checkout <your-branch>
git pull origin main          # sync with latest
# ... work ...
git add -A
git commit -m "feat: description"
git push origin <your-branch>
# → Open PR to main on GitHub
```

---

## Common Tasks

### Add a new API endpoint
1. Add route in `server.py` with `@app.route` + `@require_auth`
2. Frontend calls via `apiFetch('/api/your-endpoint', { method: 'POST', body: ... })`

### Modify the profile page
- All UI is in `dashboard/src/App.jsx` → `function ProfilePage`
- Profile dropdown, sections (personal info, experiences, skills, etc.)

### Modify job scoring
- Edit `src/scoring.py` → `evaluate_offer()` function
- Adjust weights, thresholds, or add new dimensions

### Test PDF parsing locally
```bash
source venv/bin/activate
python -c "
import pdfplumber
with pdfplumber.open('path/to/cv.pdf') as pdf:
    for i, p in enumerate(pdf.pages):
        print(f'Page {i+1}: {len(p.extract_text() or \"\")} chars')
"
```
