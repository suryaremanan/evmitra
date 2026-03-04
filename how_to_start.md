# EV Mitra - How to Start

## Project structure
- `src/backend.py`: FastAPI backend server
- `src/synthesis.py`: scoring and LLM synthesis pipeline
- `src/car_profiles.py`: EV model profiles
- `src/user_store.py`: SQLite profile/history store
- `data/`: static charger and Team-BHP JSON files
- `frontend/index.html`: browser UI

## 1) Create and activate a virtual environment (recommended)
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2) Install dependencies
```bash
pip install -r requirements.txt
```

If you prefer manual install:
```bash
pip install fastapi uvicorn requests pydantic python-dotenv anthropic
```

## 3) Configure environment variables
Create a `.env` file in the project root (`evmitra/.env`) and set at least:
```env
TINYFISH_API_KEY=your_tinyfish_key
ANTHROPIC_API_KEY=your_anthropic_key
# Optional fallback
# FIREWORKS_API_KEY=your_fireworks_key
```

## 4) Start the backend
From the project root:
```bash
python src/backend.py
```

Backend endpoints:
- API: `http://localhost:8080`
- Docs: `http://localhost:8080/docs`
- Health: `http://localhost:8080/health`

## 5) Start the frontend
In a new terminal:
```bash
cd frontend
python3 -m http.server 5500
```

Then open:
- `http://localhost:5500/index.html`

## Notes
- The backend reads static data from `data/`.
- If live scraping fails, the app falls back to static JSON data.
- User profile/history data is stored locally in `ev_mitra_users.db`.
