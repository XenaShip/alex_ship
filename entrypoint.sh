#!/bin/bash
set -e

echo "Waiting for PostgreSQL..."
until python -c "import psycopg2; psycopg2.connect(host='$POSTGRES_HOST', port=$POSTGRES_PORT, user='$POSTGRES_USER', password='$POSTGRES_PASSWORD', dbname='$POSTGRES_DB')" 2>/dev/null
do
    echo 'Postgres is unavailable - sleeping'
    sleep 0.5
done

echo "Postgres is up!"

echo "Running migrations..."
python manage.py migrate --noinput

echo "Collecting static..."
python manage.py collectstatic --noinput

echo "Starting Gunicorn..."
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3
