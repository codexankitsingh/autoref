# AutoRef Backend

## Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy env template and configure
cp .env.example .env

# Run server
uvicorn main:app --reload --port 8000
```

## Render deploy

- **Root directory:** `backend`
- **Build:** `pip install --upgrade pip && pip install -r requirements.txt`
- **Start:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
- **Health check:** `/health`
- Set `DATABASE_URL` to your Supabase/Postgres connection string (Session mode, SSL).
- Set `ENABLE_JOB_SCRAPER=false` on free tier (scraper needs `requirements-scraper.txt`, ~100MB+ deps).
- Pin `google-genai==1.55.0` — do not use `>=1.0.0` (Render build timeout from pip backtracking).

See repo root `render.yaml` for a full blueprint.

## Local job scraper (optional)

```bash
pip install -r requirements-scraper.txt
```

## API Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health
