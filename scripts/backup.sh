#!/usr/bin/env bash
# Nightly pg_dump to GCS. Runs on the VM from cron at 03:00 local.
# Fails loudly and non-zero: a backup script that fails quietly is worse than none, because it
# is trusted. Creates no GCS bucket and grants no IAM; both are documented in README.md.
set -euo pipefail

cd "$(dirname "$0")/.."
set -a; . ./.env; set +a

: "${BACKUP_BUCKET:?set BACKUP_BUCKET in .env}"
: "${DB_NAME:?}" "${DB_USERNAME:?}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"
MIN_FREE_MB="${BACKUP_MIN_FREE_MB:-2048}"
STAMP="$(date +%Y-%m-%d)"
DUMP="/var/backups/brain/${DB_NAME}-${STAMP}.sql.gz"

free_mb=$(df -BM --output=avail /var/backups | tail -1 | tr -dc '0-9')
if [ "$free_mb" -lt "$MIN_FREE_MB" ]; then
  echo "backup aborted: ${free_mb}MB free, need ${MIN_FREE_MB}MB. A full disk corrupts Postgres." >&2
  exit 1
fi

# pg_dump runs inside the container, so the host needs no postgres client installed.
docker compose exec -T postgres pg_dump -U "$DB_USERNAME" -d "$DB_NAME" | gzip > "$DUMP"

# An empty or truncated dump restores as an empty database, silently. Check before uploading.
if [ ! -s "$DUMP" ] || [ "$(stat -c%s "$DUMP")" -lt 1024 ]; then
  echo "backup aborted: ${DUMP} is empty or implausibly small" >&2
  rm -f "$DUMP"
  exit 1
fi

gcloud storage cp "$DUMP" "gs://${BACKUP_BUCKET}/$(basename "$DUMP")"
find /var/backups/brain -name '*.sql.gz' -mtime "+${KEEP_DAYS}" -delete

echo "backed up $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1)) to gs://${BACKUP_BUCKET}/"
