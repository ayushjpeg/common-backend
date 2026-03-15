#!/usr/bin/env bash
set -euo pipefail

required_vars=(
  APP_DATABASE_URL
  RCLONE_CONFIG
)

for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required variable: $var_name" >&2
    exit 1
  fi
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/backups}"
BACKUP_RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-7}"
VERIFY_REMOTE="${VERIFY_REMOTE:-true}"
RCLONE_REMOTE="${RCLONE_REMOTE:-gdrive}"
RCLONE_DESTINATION="${RCLONE_DESTINATION:-postgres-backups/task_ops}"

if ! command -v rclone >/dev/null 2>&1; then
  echo "rclone is required but not installed" >&2
  exit 1
fi

db_url="$APP_DATABASE_URL"
db_url="${db_url/postgresql+psycopg2:/postgresql:}"
db_url="${db_url/host.docker.internal/localhost}"

rclone_config_dir="${RCLONE_CONFIG_DIR:-$HOME/.config/rclone}"
rclone_config_file="$rclone_config_dir/rclone.conf"
mkdir -p "$rclone_config_dir"
RCLONE_CONFIG_BLOB="$RCLONE_CONFIG"
unset RCLONE_CONFIG
printf '%s\n' "$RCLONE_CONFIG_BLOB" > "$rclone_config_file"
chmod 600 "$rclone_config_file"

mkdir -p "$BACKUP_DIR"

timestamp="$(date +%F_%H-%M-%S)"
db_name="$(printf '%s' "$db_url" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"
dump_file="$BACKUP_DIR/${db_name}_$timestamp.dump"
remote_path="${RCLONE_REMOTE}:${RCLONE_DESTINATION%/}/$(basename "$dump_file")"

echo "[$(date --iso-8601=seconds)] Dumping database to $dump_file"
pg_dump "$db_url" \
  -Fc \
  -f "$dump_file"

echo "[$(date --iso-8601=seconds)] Uploading dump to $remote_path"
rclone copyto "$dump_file" "$remote_path"

if [[ "$VERIFY_REMOTE" == "true" ]]; then
  echo "[$(date --iso-8601=seconds)] Verifying remote upload"
  rclone ls "$remote_path" >/dev/null
fi

find "$BACKUP_DIR" -type f -name "${db_name}_*.dump" -mtime "+$BACKUP_RETENTION_DAYS" -delete

echo "[$(date --iso-8601=seconds)] Backup completed successfully"