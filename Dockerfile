# ==============================================================================
# EduConnect Production Container Image
# Multi-tenant School & College Management Platform
# ==============================================================================

FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    DJANGO_ENV=production

# Install system dependencies (build tools & font libraries for reportlab/pdf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency requirements first to leverage Docker layer caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appuser /app

USER appuser

# Run static files collection during build
RUN DJANGO_ENV=development python manage.py collectstatic --noinput

# Expose default HTTP port
EXPOSE 8000

# Healthcheck probe using the built-in health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

# Production WSGI application server
CMD ["gunicorn", "educonnect.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
