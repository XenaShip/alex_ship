FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Сначала копируем зависимости
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 2. Теперь копируем entrypoint.sh ОТДЕЛЬНО
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh

# 3. Теперь уже копируем весь проект — и entrypoint.sh не будет перезаписан!
COPY . /app

RUN mkdir -p /app/staticfiles /app/media

CMD ["/app/entrypoint.sh"]
