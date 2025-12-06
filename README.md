# Unified Backend (FastAPI)

Central FastAPI service that powers the Tasks, Food, Gym, and CCTV frontends. It exposes REST endpoints for scheduling data plus media upload endpoints that write to local storage and persist metadata in PostgreSQL.

## Stack

- FastAPI + Uvicorn
- SQLAlchemy 2.0 ORM
- Alembic for database migrations
- PostgreSQL for structured data
- Local filesystem (configurable) for food images and CCTV recordings

## Project layout

```
app/
  core/         # settings, database session, auth helpers
  models/       # SQLAlchemy models
  schemas/      # Pydantic DTOs
  routers/      # FastAPI routers grouped by domain
  services/     # Media storage helpers
  main.py       # FastAPI entrypoint
alembic/        # Migration environment + versions
requirements.txt
README.md
```

## Getting started

1. **Create a Python virtual environment**

```bash
cd common-backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment variables**

Create a `.env` file in the project root (values below are defaults):

```
APP_DATABASE_URL=postgresql+psycopg2://task_user:task_password@localhost:5432/task_ops
APP_MEDIA_ROOT=./storage
APP_ALLOWED_ORIGINS=["http://localhost:8006","https://tasks.ayux.in"]
APP_API_KEY=super-secret-key
```

3. **Run migrations**

```bash
alembic upgrade head
```

4. **Start the API**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8007
```

The API will now respond at `http://localhost:8007/api/...`.

> **Note:** Alembic migrations will create the database *schema*, but PostgreSQL itself must already be running. Create the `task_ops` database (or update `APP_DATABASE_URL`) before running `alembic upgrade head`.

When deploying through GitHub Actions on a self-hosted runner, set `APP_DATABASE_URL` to use `host.docker.internal` (e.g., `postgresql+psycopg2://task_user:task_password@host.docker.internal:5432/task_ops`). The workflow adds that host mapping so containers can reach the host OS database.

## Media storage

Uploads are saved under `APP_MEDIA_ROOT` (defaults to `backend/storage`). Each owner type (food, cctv, etc.) gets its own subfolder. In production, point `APP_MEDIA_ROOT` to a persistent path mounted from your Linux server or swap the implementation for S3/MinIO.

## Next steps

- Host this backend + PostgreSQL on your Linux server (Docker or bare-metal) and expose it with HTTPS. A ready-made workflow for your self-hosted runner lives at `.github/workflows/deploy.yml`.
- Share the API base URL + `X-API-Key` with each frontend so we can wire their data sources to these endpoints.
- Extend the routers with any app-specific logic (e.g., CCTV streaming controls) once the core plumbing is running.
