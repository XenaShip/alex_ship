FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Дать права на выполнение entrypoint
RUN chmod +x /app/entrypoint.sh

# Создаем нужные директории
RUN mkdir -p /app/staticfiles /app/media

# ВАЖНО: НЕ СТИРАТЬ entrypoint Docker'а!
# Убери ENTRYPOINT [] полностью.
# Docker-compose сам подставит нужный entrypoint.
