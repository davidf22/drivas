# ── Stage 1: Build dependencies ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# System deps needed to compile packages (psycopg2, Pillow)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# ── Stage 2: Runtime image ─────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# Install wheels built in previous stage (no compiler needed)
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*

COPY . .

# Collect static files at build time (needs a dummy SECRET_KEY)
RUN SECRET_KEY=build-phase-placeholder \
    DEBUG=False \
    DATABASE_URL=sqlite:///tmp/build.db \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Entrypoint: run migrations then start gunicorn
CMD ["sh", "-c", "python manage.py migrate --noinput && \
    gunicorn drivas.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --threads 2 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile -"]
