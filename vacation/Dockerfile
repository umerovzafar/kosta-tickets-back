FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 1244

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "1244", "--no-access-log", "--log-level", "critical"]
