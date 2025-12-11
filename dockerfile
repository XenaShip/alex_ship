FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Копируем requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# 2. Копируем entrypoint отдельно в /usr/local/bin — НЕ ЗАТРЁТСЯ!
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 3. Копируем весь проект
COPY . /app/

CMD ["entrypoint.sh"]
