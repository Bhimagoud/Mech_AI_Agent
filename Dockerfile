# ─────────────────────────────────────────────────────────────────
#  NBA PEO-Mission Mapping Engine — Dockerfile
#  Target: Google Cloud Run (fully managed, serverless containers)
# ─────────────────────────────────────────────────────────────────

# ── Stage 1: dependency builder ──────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by some packages (e.g. pdfplumber C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: lean runtime image ──────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user for security
RUN useradd --create-home appuser
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Set cache directory for Hugging Face models
ENV HF_HOME=/app/.cache

# Pre-download RAG embedding model so it's baked into the image
RUN mkdir -p /app/.cache && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && \
    chown -R appuser:appuser /app/.cache

# Copy project source
COPY --chown=appuser:appuser agents/      agents/
COPY --chown=appuser:appuser services/    services/
COPY --chown=appuser:appuser templates/   templates/
COPY --chown=appuser:appuser static/      static/
COPY --chown=appuser:appuser orchestrator.py .
COPY --chown=appuser:appuser app.py .

USER appuser

# Cloud Run injects $PORT at runtime (default 8080).
# Flask reads it via os.environ.get("PORT", 5000)
ENV PORT=8080
EXPOSE 8080

# Use gunicorn for production (more robust than Flask's dev server)
CMD ["python", "-m", "gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--timeout", "120", \
     "app:app"]
