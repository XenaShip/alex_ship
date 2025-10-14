#!/usr/bin/env sh
set -e

# Ждём БД (healthcheck уже помогает; можно оставить пустым)
# sleep 2

# Миграции
python manage.py migrate --noinput || {
  echo "Migrations failed"; exit 1;
}

# Собираем статику (чтобы админка имела стили/иконки)
python manage.py collectstatic --noinput || {
  echo "Collectstatic failed"; exit 1;
}

exec "$@"
