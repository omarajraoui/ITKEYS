# Mass Apply

AI-powered job application tool. Scans 7 job boards, generates tailored CVs and cover letters for each offer using Claude AI.

## Architecture

```
mass/
├── dashboard/          # React frontend (Vite + Tailwind)
│   ├── src/App.jsx     # Main app (sidebar, offers, kanban, templates)
│   ├── src/Auth.jsx    # Supabase auth (Google OAuth + email/password)
│   └── src/index.css   # Design system (CSS variables)
├── src/
│   ├── scraper/        # Job board scrapers (WTTJ, APEC, Adzuna, LinkedIn, France Travail, PMEjob, CSP)
│   ├── compiler/       # LaTeX → PDF compilation
│   ├── generator.py    # Claude AI generation (CV + cover letter)
│   ├── embeddings.py   # Semantic scoring with sentence-transformers
│   └── tracker.py      # SQLite application tracking
├── server.py           # Flask API (auth, offers, generation SSE, batch, templates)
├── scan_jobs.py        # Job scanning orchestrator
├── templates/          # LaTeX templates (cv_master.tex, letter_master.tex)
├── data/               # Global data (scan_results.json, truth.json)
│   └── users/          # Per-user data (truth.json, preferences.json, scan_results.json)
└── .env                # API keys (Anthropic, Supabase, Adzuna, Gemini)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 19, Vite, Tailwind CSS, DM Sans |
| Backend | Flask (Python 3.13) |
| Auth | Supabase (Google OAuth + email/password) |
| AI | Anthropic API (Haiku for generation, Sonnet for modifications) |
| CV Parsing | Anthropic Haiku + pypdf |
| Scoring | Keyword matching + sentence-transformers embeddings (all-MiniLM-L6-v2) |
| PDF | pdflatex (TexLive) |
| Scrapers | requests + BeautifulSoup, parallel with ThreadPoolExecutor |

## Setup

### Prerequisites

- Python 3.13+
- Node.js 18+
- pdflatex (TexLive): `brew install --cask mactex` or install BasicTeX
- Google Chrome (optional, for Indeed scraper — currently disabled)

### Installation

```bash
# Clone
git clone <repo-url>
cd mass

# Backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd dashboard
npm install
cd ..

# Environment
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_JWT_SECRET
```

### Running

```bash
# Terminal 1: Backend
source venv/bin/activate
python server.py
# → http://localhost:5001

# Terminal 2: Frontend
cd dashboard
npm run dev
# → http://localhost:5173
```

### Environment Variables

```env
# Required
ANTHROPIC_API_KEY=sk-ant-api03-...    # Claude AI for CV/letter generation
SUPABASE_URL=https://xxx.supabase.co  # Auth
SUPABASE_ANON_KEY=eyJ...              # Auth
SUPABASE_JWT_SECRET=xxx               # JWT verification

# Optional
ADZUNA_APP_ID=xxx                     # Job board aggregator
ADZUNA_APP_KEY=xxx
GEMINI_API_KEY=xxx                    # CV parsing fallback
ADMIN_EMAILS=email1@gmail.com,email2@gmail.com  # Skip onboarding, use hardcoded config
```

## Features

### For Users
- **Onboarding**: Pick domain preset, add keywords, select experience range → instant job feed
- **8 Job Sources**: WTTJ, France Travail, LinkedIn, APEC, Adzuna, PMEjob, CSP (parallel scanning)
- **Semantic Scoring**: Offers ranked by cosine similarity (sentence-transformers) + keyword matching
- **CV Generation**: Upload CV once, AI adapts it per offer (Haiku = fast/cheap, Sonnet = modifications)
- **Preview Page**: Side-by-side PDF preview + chat-style prompt for modifications
- **Batch Generation**: Like offers, generate all at once in background
- **Kanban Tracking**: Track application status (generated → applied → interview → offer)

### For Admin (Omar)
- Hardcoded scoring + queries for specific profile
- Technicien tab (separate job search for support roles)
- Original LaTeX templates

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/profile` | User onboarding status |
| PUT | `/api/profile/truth` | Upload/update CV (truth.json) |
| GET/PUT | `/api/profile/preferences` | Job search preferences |
| GET | `/api/offers` | Scored offers (per-user) |
| POST | `/api/scan` | Trigger job scan |
| GET | `/api/scan/status` | Scan progress |
| POST | `/api/generate` | Generate CV+letter (SSE stream) |
| POST | `/api/batch-generate` | Batch generation (background) |
| GET | `/api/batch-generate/status` | Batch progress |
| POST | `/api/parse-cv` | Parse CV from PDF/text |
| GET | `/api/templates` | Get LaTeX templates |
| PUT | `/api/templates` | Update templates |
| GET | `/api/templates/preview/:kind` | Compile + preview template PDF |
| GET | `/api/applications` | Kanban data |
| PATCH | `/api/applications/:id/status` | Update status |
| GET | `/api/download/:path` | Download PDF |

## Working with Claude Code

### For teammates using Claude Code

1. **Read CLAUDE.md** first — it contains all project-specific rules for CV/letter generation
2. **Use the installed skills**:
   - `frontend-design` — for UI work
   - `api-design` — for API changes
   - `deployment-patterns` — for DevOps
   - `ui-ux-pro-max` — for design decisions (query with scripts in .agents/skills/)
3. **Don't modify scoring for admin** — Omar's hardcoded scoring is intentional
4. **Test with a non-admin account** — create one with email/password, not Google OAuth
5. **After changes**: `cd dashboard && npx vite build` to verify frontend builds

### Key files to understand

| File | What it does | Touch carefully? |
|------|-------------|-----------------|
| `src/generator.py` | AI generation pipeline — SYSTEM_PROMPT, validation, Claude API calls | Yes — Omar-specific rules |
| `src/scraper/__init__.py` | All 7 scrapers + scoring engine | Yes — scoring affects all users |
| `src/embeddings.py` | Semantic scoring with sentence-transformers | Low risk |
| `src/compiler/__init__.py` | LaTeX compilation | Medium — template placeholders |
| `server.py` | All API endpoints, auth, SSE | Yes — auth logic is critical |
| `dashboard/src/App.jsx` | Entire frontend (2096 lines) | Needs splitting into components |
| `dashboard/src/index.css` | Design system (CSS variables) | Low risk |
| `scan_jobs.py` | Scan orchestrator | Low risk |

## Known Issues / TODOs

- [ ] App.jsx needs splitting into separate component files
- [ ] No tests (unit or integration)
- [ ] No error boundaries in React
- [ ] Freelance platform scraping not available (Malt/Free-Work block requests)
- [ ] LaTeX templates are Omar-specific — need generic templates for other users
- [ ] No proper caching (scan results re-scored on every page load)
- [ ] SQLite for tracking — needs PostgreSQL for production
- [ ] Sentence-transformers model loads on first request (~3s delay)

## Cost Estimation

| Action | Model | Cost |
|--------|-------|------|
| CV+Letter generation | Haiku 4.5 | ~$0.01 |
| Modification with prompt | Sonnet 4 | ~$0.04 |
| CV parsing from PDF | Haiku 4.5 | ~$0.01 |
| 10 generations/day | Mostly Haiku | ~$3/month |
| 50 generations/day | Mostly Haiku | ~$16/month |
