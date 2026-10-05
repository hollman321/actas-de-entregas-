#!/bin/sh
set -eu

sh /app/scripts/backup_database.sh before-migration
python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers 3 \
    --access-logfile - \
    --error-logfile -
