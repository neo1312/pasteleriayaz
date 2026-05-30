#!/bin/sh

set -e

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
    echo "Waiting for PostgreSQL..."
    sleep 2
done
echo "PostgreSQL is ready."

python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn bakery.wsgi:application \
    --bind 0.0.0.0:8002 \
    --workers 3 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -
