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

## Nightly backup to Aiven

If you want the database backup workflow to live with this project, use the host-run script in `scripts/backup_to_aiven.sh`. This keeps backup logic inside the `common-backend` repo without embedding a scheduler in the FastAPI process.

1. Copy the environment template and fill in your credentials.

```bash
cd common-backend
cp scripts/backup_to_aiven.env.example scripts/backup_to_aiven.env
chmod 600 scripts/backup_to_aiven.env
```

2. Review `scripts/backup_to_aiven.env` and set:

```bash
LOCAL_HOST=localhost
LOCAL_PORT=5432
LOCAL_DB=task_ops
LOCAL_USER=task_user
LOCAL_PASSWORD=...

AIVEN_HOST=...
AIVEN_PORT=...
AIVEN_DB=...
AIVEN_USER=...
AIVEN_PASSWORD=...
AIVEN_SSLMODE=require
```

3. Make the script executable and test it manually.

```bash
chmod +x scripts/backup_to_aiven.sh
./scripts/backup_to_aiven.sh
```

4. Add a host cron entry on your Ubuntu server.

```cron
30 2 * * * cd /path/to/common-backend && ./scripts/backup_to_aiven.sh >> /var/log/common-backend-db-backup.log 2>&1
```

This job performs a local `pg_dump`, restores that dump into the Aiven PostgreSQL database, and removes local dump files older than `BACKUP_RETENTION_DAYS`.

Important: this backs up PostgreSQL data only. It does not back up media files under `APP_MEDIA_ROOT`.

## Next steps

- Host this backend + PostgreSQL on your Linux server (Docker or bare-metal) and expose it with HTTPS. A ready-made workflow for your self-hosted runner lives at `.github/workflows/deploy.yml`.
- Extend the routers with any app-specific logic (e.g., CCTV streaming controls) once the core plumbing is running.
