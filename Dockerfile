# Use official Python runtime as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (optional but good practice)
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY . .

# Expose the port (Railway uses PORT env)
EXPOSE 8000

# Healthcheck (simple curl to /health)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
 CMD curl -f http://127.0.0.1:${PORT:-8000}/health || exit 1

# Run the app
CMD ["sh","-c","uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]