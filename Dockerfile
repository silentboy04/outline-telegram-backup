FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backup.py .

# Default: run once (for cron/scheduler). Override CMD for periodic.
ENTRYPOINT ["python", "backup.py"]
