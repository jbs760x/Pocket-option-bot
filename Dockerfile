# Playwright image includes Chromium & all deps we need for real trades
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# bring in our code
COPY . .

# start long-polling bot (no web server, no webhook headaches)
CMD ["python","-u","bot.py"]
