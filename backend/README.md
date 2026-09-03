# VectorEye Backend

FastAPI + SQLAlchemy + PostGIS (Neon) service that turns orthophotos into
QC-able vector features.

## Endpoints

| Method | Path                          | Purpose                                   |
|--------|-------------------------------|-------------------------------------------|
| POST   | `/api/upload`                 | Upload a GeoTIFF, run pipeline, return job |
| GET    | `/api/orthophoto/{id}`        | Orthophoto metadata                        |
| GET    | `/api/orthophoto/{id}/image`  | Original GeoTIFF (map overlay)             |
| GET    | `/api/features/{type}`        | GeoJSON FeatureCollection per class        |
| PATCH  | `/api/features/{id}`          | Approve / reject a feature                 |
| GET    | `/api/export/{type}`          | Download GeoJSON of non-rejected features  |
| GET    | `/api/health`                 | Health check                               |

`{type}` ∈ `buildings | roads | water | trees | farms`

`GET /api/features/{type}` accepts `?min_confidence=0.5` and `?status=pending`.

## Setup

```bash
cd backend
python -m venv .venv
# Windows: .\.venv\Scripts\activate   |  Linux/mac: source .venv/bin/activate
pip install -r requirements.txt      # core web + geospatial deps
cp .env.example .env                 # fill in DATABASE_URL (Neon)
python -m pip install -r requirements-ml.txt   # optional: torch/LangSAM/DeepForest
```

## Run

```bash
python run.py            # uvicorn app.main:app --reload on :8000
# or
uvicorn app.main:app --reload
```

Docs: http://localhost:8000/docs

## Notes

- The DB must have the PostGIS extension enabled. `app/main.py` tries
  `CREATE EXTENSION IF NOT EXISTS postgis` on startup.
- Features are stored as EPSG:4326 `GEOMETRY` in order to render directly on
  the Leaflet frontend.
- With `ML_ENABLED=0` (default) the pipeline returns deterministic demo
  features so the QC UI is testable without torch installed.