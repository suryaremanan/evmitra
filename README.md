# EV Mitra

EV Mitra is an honest EV decision assistant for Indian buyers. It combines real-world owner insights, charging-network availability, and a scoring pipeline to generate practical EV buying verdicts.

## Repository layout
- `src/`: Python backend and synthesis logic
- `data/`: static fallback data (chargers + owner insights)
- `frontend/`: web UI (`index.html`)
- `how_to_start.md`: full startup guide
- `requirements.txt`: Python dependencies

## Quick start
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python src/backend.py
```

Then in another terminal:
```bash
cd frontend
python3 -m http.server 5500
```

Open `http://localhost:5500/index.html`.

## Environment variables
Create `.env` in repo root:
```env
TINYFISH_API_KEY=your_tinyfish_key
ANTHROPIC_API_KEY=your_anthropic_key
# Optional fallback
# FIREWORKS_API_KEY=your_fireworks_key
# Optional DB override (defaults to /tmp on Vercel)
# EV_MITRA_DB_PATH=/tmp/ev_mitra_users.db
```

## Notes
- Backend API runs on `http://localhost:8080`.
- API docs available at `http://localhost:8080/docs`.
- If live scraping fails, static `data/` fallback is used.

## Deploy on Vercel (full stack)

This repository is set up for a 2-project Vercel deployment:

- Backend project (repo root): FastAPI serverless function via `api/index.py` and `vercel.json`
- Frontend project (`frontend-next`): Next.js app

### 1) Deploy backend (FastAPI)
1. In Vercel, create a new project from this repo.
2. Set **Root Directory** to `/` (repo root).
3. Add environment variables:
	- `TINYFISH_API_KEY`
	- `ANTHROPIC_API_KEY`
	- `FIREWORKS_API_KEY` (optional)
4. Deploy and note backend URL, e.g. `https://evmitra-api.vercel.app`.

Notes:
- On Vercel, SQLite is stored in `/tmp/ev_mitra_users.db` (ephemeral).
- User history/profile data is not persistent across cold starts/redeploys.

### 2) Deploy frontend (Next.js)
1. Create another Vercel project from the same repo.
2. Set **Root Directory** to `frontend-next`.
3. Add env vars:
	- `BACKEND_API_URL=https://<your-backend-domain>`
	- `NEXT_PUBLIC_API_URL=/api`
4. Deploy.

Why both vars:
- `NEXT_PUBLIC_API_URL=/api` keeps browser calls same-origin.
- `BACKEND_API_URL` enables Next.js rewrite proxy from `/api/*` to backend.

### 3) Optional production domain
1. Attach your custom domain to the frontend project.
2. Keep backend on Vercel domain or attach a separate API subdomain.
3. If backend domain changes, update frontend `BACKEND_API_URL` and redeploy.
