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
```

## Notes
- Backend API runs on `http://localhost:8080`.
- API docs available at `http://localhost:8080/docs`.
- If live scraping fails, static `data/` fallback is used.
