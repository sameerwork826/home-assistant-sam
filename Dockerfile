FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt pyproject.toml /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY cloud/ /app/cloud/
COPY alexa_skill/ /app/alexa_skill/

EXPOSE 8000

CMD ["uvicorn", "cloud.app:app", "--host", "0.0.0.0", "--port", "8000"]
