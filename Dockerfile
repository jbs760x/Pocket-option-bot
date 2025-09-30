# Use Playwright’s Python image so Chromium & deps are preinstalled
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

# Make Python behave well in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps first (better caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bring in the app code
COPY . .

# (Optional) quick health probe to help you debug if it boots
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python - <<'PY' || exit 1
import os,sys,urllib.request
u=f"http://127.0.0.1:{os.getenv('PORT','8000')}/health"
try:
    urllib.request.urlopen(u, timeout=3)
    sys.exit(0)
except Exception:
    sys.exit(1)
PY

# IMPORTANT: bind to Railway’s provided port (falls back to 8000 locally)
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]