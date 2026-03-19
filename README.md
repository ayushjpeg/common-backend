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
APP_PUBLIC_BASE_URL=https://common-backend.ayux.in
APP_AUTH_SECRET_KEY=replace-with-a-random-secret
APP_GOOGLE_CLIENT_ID=
APP_GOOGLE_CLIENT_SECRET=
APP_AUTH_COOKIE_DOMAIN=.ayux.in
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

## Google authentication

The backend now owns authentication for Food, Gym, and Tasks. Frontends redirect users to the backend's Google OAuth flow, and the backend returns a signed session cookie scoped for your `*.ayux.in` apps.

Required settings:

- `APP_PUBLIC_BASE_URL`: public HTTPS URL for the backend, for example `https://common-backend.ayux.in`
- `APP_AUTH_SECRET_KEY`: long random string used to sign session and OAuth state tokens
- `APP_GOOGLE_CLIENT_ID`: Google OAuth web application client ID
- `APP_GOOGLE_CLIENT_SECRET`: matching Google OAuth client secret
- `APP_AUTH_COOKIE_DOMAIN`: cookie domain, usually `.ayux.in`

Google Cloud Console setup:

1. Create an OAuth 2.0 Web Application credential.
2. Add these JavaScript origins:
  - `https://food.ayux.in`
  - `https://gym.ayux.in`
  - `https://tasks.ayux.in`
  - `https://common-backend.ayux.in`
3. Add this redirect URI:
  - `https://common-backend.ayux.in/api/auth/google/callback`

Production GitHub secrets needed by `.github/workflows/deploy.yml`:

- `APP_DATABASE_URL`
- `APP_ALLOWED_ORIGINS`
- `APP_MEDIA_ROOT`
- `APP_PUBLIC_BASE_URL`
- `APP_AUTH_SECRET_KEY`
- `APP_GOOGLE_CLIENT_ID`
- `APP_GOOGLE_CLIENT_SECRET`
- `APP_AUTH_COOKIE_DOMAIN`

## Media storage

Uploads are saved under `APP_MEDIA_ROOT` (defaults to `backend/storage`). Each owner type (food, cctv, etc.) gets its own subfolder. In production, point `APP_MEDIA_ROOT` to a persistent path mounted from your Linux server or swap the implementation for S3/MinIO.

## Nightly database backup to Google Drive

If you want the backup workflow to live entirely inside this project and use GitHub secrets instead of a local env file, use:

- `scripts/backup_to_gdrive.sh`
- `.github/workflows/backup-to-gdrive.yml`

The workflow runs nightly on your self-hosted Linux runner and uses the same `APP_DATABASE_URL` secret you already use for deployment.

Required GitHub secrets:

1. `APP_DATABASE_URL`

Use the same value already configured for deployment. The backup script normalizes the SQLAlchemy URL format and converts `host.docker.internal` to `localhost` so `pg_dump` works from the host runner.

2. `RCLONE_CONFIG`

Store the full contents of your `rclone.conf` file as a GitHub secret. To create it on the server:

```bash
rclone config
cat ~/.config/rclone/rclone.conf
```

Copy that file content into the `RCLONE_CONFIG` GitHub secret.

Default Google Drive target used by the workflow:

```text
remote: gdrive
folder: postgres-backups/task_ops
```

The scheduled run is currently:

```text
30 2 * * *
```

If you want to test it immediately, trigger the `Backup Database To Google Drive` workflow manually with `workflow_dispatch`.

This job performs a `pg_dump`, uploads the dump file to Google Drive through `rclone`, verifies the remote upload, and removes old local dump files from the runner workspace.

Important: this backs up PostgreSQL data only. It does not back up media files under `APP_MEDIA_ROOT`.

## Next steps

- Host this backend + PostgreSQL on your Linux server (Docker or bare-metal) and expose it with HTTPS. A ready-made workflow for your self-hosted runner lives at `.github/workflows/deploy.yml`.
- Extend the routers with any app-specific logic (e.g., CCTV streaming controls) once the core plumbing is running.
