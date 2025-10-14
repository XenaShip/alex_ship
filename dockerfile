# Базовый образ
FROM python:3.12-slim

# Не буферизуем вывод и отключаем .pyc
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POETRY_VIRTUALENVS_CREATE=false

# Системные зависимости для psycopg2 и компиляции
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Если используешь requirements.txt
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# Если используешь Poetry — раскомментируй ниже и закомментируй блок с requirements.txt
# COPY pyproject.toml poetry.lock* /app/
# RUN pip install poetry && poetry install --no-interaction --no-ansi

# Копируем проект
COPY . /app

# На всякий случай создаём директории для статики/медиа
RUN mkdir -p /app/static /app/media

# entrypoint для миграций и collectstatic
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh
