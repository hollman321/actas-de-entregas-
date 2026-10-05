#!/bin/sh
set -eu

label=${1:-scheduled}
case "$label" in
    ''|*[!a-zA-Z0-9_-]*)
        echo "Backup label must contain only letters, digits, underscores, or hyphens." >&2
        exit 2
        ;;
esac

: "${APP_ENV:?APP_ENV must be set}"
: "${DB_HOST:?DB_HOST must be set}"
: "${DB_NAME:?DB_NAME must be set}"
: "${DB_USER:?DB_USER must be set}"
: "${DB_PASSWORD:?DB_PASSWORD must be set}"

case "$APP_ENV" in
    production) environment=production ;;
    test|testing|staging) environment=test ;;
    *)
        echo "Unsupported APP_ENV for backups: $APP_ENV" >&2
        exit 2
        ;;
esac

backup_root=${BACKUP_ROOT:-/backups}
backup_directory="${backup_root}/${environment}"
mkdir -p "$backup_directory"
umask 077
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
temporary_file=$(mktemp "${backup_directory}/${environment}_${label}_${timestamp}_XXXXXX.partial")
trap 'rm -f "$temporary_file"' EXIT HUP INT TERM

export PGPASSWORD="$DB_PASSWORD"
pg_dump \
    --host="$DB_HOST" \
    --port="${DB_PORT:-5432}" \
    --username="$DB_USER" \
    --dbname="$DB_NAME" \
    --format=custom \
    --no-owner \
    --no-acl \
    --file="$temporary_file"

pg_restore --list "$temporary_file" >/dev/null
backup_file="${temporary_file%.partial}.dump"
mv "$temporary_file" "$backup_file"
trap - EXIT HUP INT TERM
echo "Database backup completed: $backup_file"
