# Use Playwright base image (includes Chromium)
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

# Prevents .pyc files + forces log flushing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bring in code
COPY . .

# Start bot (long-polling)
CMD ["python", "-u", "bot.py"]