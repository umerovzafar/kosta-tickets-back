FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Windows CRLF в скрипте ломает shebang в Linux-контейнере
RUN sed -i 's/\r$//' docker-entrypoint.sh && chmod +x docker-entrypoint.sh

EXPOSE 1242

# LOG_LEVEL: debug | info | warning | error (и для uvicorn в entrypoint, и для приложения в main.py)
ENV LOG_LEVEL=info

CMD ["./docker-entrypoint.sh"]
